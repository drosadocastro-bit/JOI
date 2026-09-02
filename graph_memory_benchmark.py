import argparse
import json
import tempfile
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import core.orchestrator as orchestrator_module
from core.orchestrator import JoiOrchestrator
from memory.artifact_integrity import verify_artifact_manifest
from memory.graph_memory import (
    EntityCandidate,
    ExplicitEntityExtractor,
    GraphEvidenceRef,
    GraphMemoryError,
    GraphMemoryManager,
    GraphMemoryStore,
    build_entity_id,
)
from memory.memory_store import EpisodicTurn, MemoryPolicyRecord


BENCHMARK = 'joi-graph-write-only-v1'


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )


def _turns(exchange: dict) -> tuple[EpisodicTurn, EpisodicTurn]:
    exchange_id = exchange['exchange_id']
    timestamp = exchange['created_at_utc']
    return (
        EpisodicTurn(
            turn_id=f'{exchange_id}-user',
            exchange_id=exchange_id,
            role='user',
            content=exchange['user'],
            created_at_utc=timestamp,
            schema_version=1,
        ),
        EpisodicTurn(
            turn_id=f'{exchange_id}-assistant',
            exchange_id=exchange_id,
            role='assistant',
            content=exchange['assistant'],
            created_at_utc=timestamp,
            schema_version=1,
        ),
    )


def _entity_key(entity_type: str, canonical_label: str) -> str:
    return f'{entity_type}:{canonical_label}'


def _evaluate_graph(
    corpus: dict,
    labels: dict,
    work_directory: Path,
) -> tuple[dict, Path, list[dict]]:
    extractor = ExplicitEntityExtractor()
    graph_path = work_directory / 'graph.json'
    manager = GraphMemoryManager(GraphMemoryStore(graph_path), extractor)
    extracted = []
    turns_by_exchange = {}
    for exchange in corpus['exchanges']:
        turns = _turns(exchange)
        turns_by_exchange[exchange['exchange_id']] = turns
        candidates = extractor.extract(turns)
        extracted.extend({
            'exchange_id': candidate.evidence.exchange_id,
            'entity_type': candidate.entity_type,
            'canonical_label': candidate.canonical_label,
            'surface_form': candidate.surface_form,
            'entity_id': candidate.entity_id,
            'turn_ids': list(candidate.evidence.turn_ids),
            'policy_ids': list(candidate.evidence.policy_ids),
            'status': candidate.status,
            'extractor_version': candidate.extractor_version,
        } for candidate in candidates)
        manager.update(turns)

    expected = {
        (
            item['exchange_id'],
            item['entity_type'],
            item['canonical_label'],
            item['surface_form'],
        )
        for item in labels['expected_entities']
    }
    actual = {
        (
            item['exchange_id'],
            item['entity_type'],
            item['canonical_label'],
            item['surface_form'],
        )
        for item in extracted
    }
    matched = expected & actual
    unsupported = actual - expected
    missing = expected - actual
    automatic_precision = len(matched) / len(actual) if actual else None
    automatic_recall = len(matched) / len(expected) if expected else None

    state = manager.state
    valid_provenance = 0
    for node in state.nodes.values():
        if all(
            source.exchange_id in turns_by_exchange
            and set(source.turn_ids).issubset({
                turn.turn_id for turn in turns_by_exchange[source.exchange_id]
            })
            and not source.suppressed
            for source in node.source_refs
        ):
            valid_provenance += 1
    provenance_coverage = valid_provenance / len(state.nodes) if state.nodes else 1.0

    expected_edges = {
        (
            item['exchange_id'],
            tuple(sorted(item['entities'])),
            item['relation'],
        )
        for item in labels['expected_edges']
    }
    actual_edges = set()
    for edge in state.edges.values():
        endpoint_labels = tuple(sorted((
            _entity_key(
                state.nodes[edge.source_node_id].entity_type,
                state.nodes[edge.source_node_id].canonical_label,
            ),
            _entity_key(
                state.nodes[edge.target_node_id].entity_type,
                state.nodes[edge.target_node_id].canonical_label,
            ),
        )))
        actual_edges.update(
            (exchange_id, endpoint_labels, edge.relation)
            for exchange_id in edge.source_exchange_ids
        )

    bytes_before_replay = graph_path.read_bytes()
    observations_before_replay = sum(
        node.observation_count for node in state.nodes.values()
    ) + sum(edge.weight for edge in state.edges.values())
    for exchange_id in corpus['replay_exchange_ids']:
        manager.update(turns_by_exchange[exchange_id])
    observations_after_replay = sum(
        node.observation_count for node in manager.state.nodes.values()
    ) + sum(edge.weight for edge in manager.state.edges.values())
    replay_added = observations_after_replay - observations_before_replay
    replay_inflation_rate = (
        replay_added / observations_before_replay
        if observations_before_replay else 0.0
    )
    replay_bytes_unchanged = graph_path.read_bytes() == bytes_before_replay

    second_path = work_directory / 'graph-replay.json'
    second_manager = GraphMemoryManager(GraphMemoryStore(second_path), extractor)
    for exchange in corpus['exchanges']:
        second_manager.update(_turns(exchange))
    deterministic_bytes = second_path.read_bytes() == bytes_before_replay
    restart_match = GraphMemoryStore(graph_path).load() == state

    policy_results = []
    for policy_case in corpus['policy_cases']:
        target_turn = turns_by_exchange[policy_case['exchange_id']][0]
        policy = MemoryPolicyRecord(
            policy_id=policy_case['policy_id'],
            target_turn_id=target_turn.turn_id,
            action=policy_case['action'],
            replacement_content=policy_case.get('replacement_content'),
            reason='frozen graph evaluation',
            supersedes_policy_id=None,
            created_at_utc=policy_case['created_at_utc'],
            schema_version=1,
        )
        before_refs = {
            (node.node_id, source.exchange_id, source.turn_ids)
            for node in manager.state.nodes.values()
            for source in node.source_refs
            if target_turn.turn_id in source.turn_ids
        }
        manager.apply_policy(policy)
        after_refs = {
            (node.node_id, source.exchange_id, source.turn_ids)
            for node in manager.state.nodes.values()
            for source in node.source_refs
            if target_turn.turn_id in source.turn_ids
            and source.suppressed
            and policy.policy_id in source.policy_ids
        }
        replacement_absent = True
        if policy.replacement_content:
            replacement_absent = all(
                node.canonical_label not in policy.replacement_content.casefold()
                or node.node_id in {item[0] for item in before_refs}
                for node in manager.state.nodes.values()
            )
        policy_results.append({
            'policy_id': policy.policy_id,
            'matching_sources_suppressed': bool(after_refs),
            'lineage_preserved': before_refs == after_refs,
            'replacement_auto_extracted': not replacement_absent,
        })

    metrics = {
        'extracted_entity_count': len(actual),
        'expected_entity_count': len(expected),
        'matched_expected_entity_count': len(matched),
        'unsupported_entity_count': len(unsupported),
        'missing_expected_entity_count': len(missing),
        'automatic_extraction_precision': automatic_precision,
        'automatic_extraction_recall': automatic_recall,
        'human_reviewed_extraction_precision': None,
        'human_review_status': 'PENDING',
        'unsupported_entity_rate': len(unsupported) / len(actual) if actual else 0.0,
        'source_provenance_coverage': provenance_coverage,
        'expected_edge_match': actual_edges == expected_edges,
        'duplicate_replay_inflation_rate': replay_inflation_rate,
        'duplicate_replay_bytes_unchanged': replay_bytes_unchanged,
        'deterministic_replay_byte_match': deterministic_bytes,
        'restart_state_match': restart_match,
        'policy_lineage_preservation': (
            sum(
                result['matching_sources_suppressed']
                and result['lineage_preserved']
                and not result['replacement_auto_extracted']
                for result in policy_results
            ) / len(policy_results)
        ),
    }
    return metrics, graph_path, extracted


def _evaluate_failure_survival(work_directory: Path) -> dict:
    work_directory.mkdir(parents=True, exist_ok=True)
    extractor = ExplicitEntityExtractor()
    base_exchange = _turns({
        'exchange_id': 'failure-control',
        'created_at_utc': '2026-09-01T13:00:00+00:00',
        'user': 'My name is Control.',
        'assistant': 'Noted.',
    })
    controls = {}

    surrogate_turns = (
        EpisodicTurn(
            turn_id='surrogate-user', exchange_id='surrogate', role='user',
            content='My name is \ud800.', created_at_utc='2026-09-01T13:01:00+00:00',
            schema_version=1,
        ),
        EpisodicTurn(
            turn_id='surrogate-assistant', exchange_id='surrogate', role='assistant',
            content='Noted.', created_at_utc='2026-09-01T13:01:00+00:00',
            schema_version=1,
        ),
    )
    try:
        GraphMemoryManager(
            GraphMemoryStore(work_directory / 'surrogate.json'), extractor
        ).update(surrogate_turns)
        controls['unpaired_surrogate_source'] = False
    except GraphMemoryError:
        controls['unpaired_surrogate_source'] = not (
            work_directory / 'surrogate.json'
        ).exists()

    class InferredExtractor:
        version = 'inferred-control-v1'

        def extract(self, turns):
            return (EntityCandidate(
                entity_id=build_entity_id('person', 'Control'),
                canonical_label='control',
                surface_form='Control',
                entity_type='person',
                evidence=GraphEvidenceRef(
                    exchange_id='failure-control',
                    turn_ids=('failure-control-user',),
                    policy_ids=(None,),
                    observed_at_utc='2026-09-01T13:00:00+00:00',
                    suppressed=False,
                ),
                extractor_version=self.version,
                status='inferred',
            ),)

    try:
        GraphMemoryManager(
            GraphMemoryStore(work_directory / 'inferred.json'), InferredExtractor()
        ).update(base_exchange)
        controls['unsupported_inferred_candidate'] = False
    except GraphMemoryError:
        controls['unsupported_inferred_candidate'] = not (
            work_directory / 'inferred.json'
        ).exists()

    class MalformedExtractor:
        version = 'malformed-control-v1'

        def extract(self, turns):
            return ({'malformed': True},)

    try:
        GraphMemoryManager(
            GraphMemoryStore(work_directory / 'malformed.json'), MalformedExtractor()
        ).update(base_exchange)
        controls['malformed_extractor_result'] = False
    except GraphMemoryError:
        controls['malformed_extractor_result'] = not (
            work_directory / 'malformed.json'
        ).exists()

    class FailingStore(GraphMemoryStore):
        def save(self, state):
            raise GraphMemoryError('simulated graph write failure')

    try:
        GraphMemoryManager(
            FailingStore(work_directory / 'write-failure.json'), extractor
        ).update(base_exchange)
        controls['graph_store_write_failure'] = False
    except GraphMemoryError:
        controls['graph_store_write_failure'] = not (
            work_directory / 'write-failure.json'
        ).exists()

    corrupt_path = work_directory / 'corrupt.json'
    corrupt_path.write_text('{broken', encoding='utf-8')
    original = corrupt_path.read_bytes()
    try:
        GraphMemoryManager(GraphMemoryStore(corrupt_path), extractor)
        controls['corrupt_graph_artifact'] = False
    except GraphMemoryError:
        controls['corrupt_graph_artifact'] = corrupt_path.read_bytes() == original

    return {
        'controls': controls,
        'surviving_count': sum(controls.values()),
        'control_count': len(controls),
        'survival_rate': sum(controls.values()) / len(controls),
    }


def _orchestrator_settings(root: Path, graph_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        app_name='JOI', lmstudio_base_url='local-test', local_model='test-double',
        request_timeout_seconds=1, voice_enabled=False, voice_mode='local',
        kokoro_python='', kokoro_model_path='', kokoro_voices_path='',
        tts_voice='', tts_language='en-us', tts_output_path='',
        tts_timeout_seconds=1, elevenlabs_voice_id='',
        elevenlabs_model_id='', elevenlabs_base_url='', elevenlabs_timeout_seconds=1,
        vision_enabled=False, cloud_enabled=False, memory_mode='persistent',
        persistent_memory_enabled=True,
        memory_store_path=str(root / 'episodic.sqlite3'),
        compact_memory_enabled=False, compact_memory_path=str(root / 'compact.json'),
        compact_memory_max_characters=2000, model_compact_memory_enabled=False,
        model_compact_memory_path=str(root / 'model.json'),
        compact_memory_evaluation_path=str(root / 'evaluation.json'),
        compact_memory_provider='local', graph_memory_enabled=graph_enabled,
        graph_memory_path=str(root / 'graph.json'), openai_model='',
        openai_base_url='', openai_timeout_seconds=1,
        credential_audit_path=str(root / 'credential-access.jsonl'),
    )


def _evaluate_behavior(work_directory: Path) -> dict:
    brain_messages = []
    fake_brain_calls = 0
    external_calls = 0
    retrieval_count = 0

    class FakeBrain:
        def chat(self, messages):
            nonlocal fake_brain_calls
            fake_brain_calls += 1
            brain_messages.append(json.loads(json.dumps(messages)))
            return 'Deterministic reply.'

        def health(self):
            return {'ok': True, 'provider': 'in-process-test-double'}

    def forbidden_external_call(*args, **kwargs):
        nonlocal external_calls
        external_calls += 1
        raise RuntimeError('external provider or network call prohibited')

    original_brain = orchestrator_module.LocalLMStudioBrain
    original_openai = orchestrator_module.OpenAICompactSummarizerProvider
    original_voice = orchestrator_module.ElevenLabsVoiceProvider
    original_urlopen = urllib.request.urlopen
    orchestrator_module.LocalLMStudioBrain = lambda *args, **kwargs: FakeBrain()
    orchestrator_module.OpenAICompactSummarizerProvider = forbidden_external_call
    orchestrator_module.ElevenLabsVoiceProvider = forbidden_external_call
    urllib.request.urlopen = forbidden_external_call
    try:
        off = JoiOrchestrator(
            _orchestrator_settings(work_directory / 'off', False),
            'system prompt',
            SimpleNamespace(info=lambda *args: None, exception=lambda *args: None),
        )
        on = JoiOrchestrator(
            _orchestrator_settings(work_directory / 'on', True),
            'system prompt',
            SimpleNamespace(
                info=lambda *args: None,
                error=lambda *args: None,
                exception=lambda *args: None,
            ),
        )
        for method_name in ('status', 'recent', 'why'):
            original = getattr(on.graph_memory_manager, method_name)

            def counted(*args, _original=original, **kwargs):
                nonlocal retrieval_count
                retrieval_count += 1
                return _original(*args, **kwargs)

            setattr(on.graph_memory_manager, method_name, counted)
        off_reply = off.chat('My name is Luna. I prefer green tea.')
        on_reply = on.chat('My name is Luna. I prefer green tea.')
        on.graph_memory_worker.wait_for_idle()
        graph_written = Path(on.settings.graph_memory_path).is_file()
        off_graph_absent = not Path(off.settings.graph_memory_path).exists()
        off.close()
        on.close()
    finally:
        orchestrator_module.LocalLMStudioBrain = original_brain
        orchestrator_module.OpenAICompactSummarizerProvider = original_openai
        orchestrator_module.ElevenLabsVoiceProvider = original_voice
        urllib.request.urlopen = original_urlopen

    return {
        'off_reply': off_reply,
        'on_reply': on_reply,
        'behavior_delta': off_reply != on_reply,
        'prompt_delta': brain_messages[0] != brain_messages[1],
        'retrieval_count': retrieval_count,
        'external_provider_network_count': external_calls,
        'deterministic_fake_brain_calls': fake_brain_calls,
        'enabled_graph_written': graph_written,
        'disabled_graph_absent': off_graph_absent,
    }


def run_graph_memory_benchmark(
    *,
    benchmark_directory: str | Path,
    output_directory: str | Path,
) -> dict:
    benchmark_directory = Path(benchmark_directory)
    output_directory = Path(output_directory)
    if output_directory.resolve() == benchmark_directory.resolve():
        raise RuntimeError('results must not overwrite frozen benchmark inputs')
    review_path = output_directory / 'human-review.json'
    if review_path.exists():
        existing_review = _read_json(review_path)
        if existing_review.get('human_review_complete'):
            raise RuntimeError('completed human review must not be overwritten')
    if verify_artifact_manifest(benchmark_directory / 'freeze-manifest.json') != 4:
        raise RuntimeError('graph evaluation freeze manifest is incomplete')
    preregistration = _read_json(benchmark_directory / 'preregistration.json')
    corpus = _read_json(benchmark_directory / 'corpus.json')
    labels = _read_json(benchmark_directory / 'expected-labels.json')
    if preregistration['status'] != 'FROZEN_NOT_EXECUTED':
        raise RuntimeError('graph evaluation was not frozen before execution')
    if preregistration['authorization_boundary']['retrieval_enabled']:
        raise RuntimeError('graph retrieval must remain disabled')

    with tempfile.TemporaryDirectory(prefix='joi-graph-eval-') as temporary:
        work_directory = Path(temporary)
        graph_metrics, graph_path, extracted = _evaluate_graph(
            corpus, labels, work_directory / 'graph'
        )
        failure_metrics = _evaluate_failure_survival(work_directory / 'failures')
        behavior_metrics = _evaluate_behavior(work_directory / 'behavior')
        output_directory.mkdir(parents=True, exist_ok=True)
        (output_directory / 'graph.json').write_bytes(graph_path.read_bytes())

    automatic_gates = {
        'automatic_extraction_precision': graph_metrics[
            'automatic_extraction_precision'
        ] == 1.0,
        'automatic_extraction_recall': graph_metrics[
            'automatic_extraction_recall'
        ] == 1.0,
        'unsupported_entity_rate': graph_metrics['unsupported_entity_rate'] == 0,
        'source_provenance_coverage': graph_metrics[
            'source_provenance_coverage'
        ] == 1.0,
        'expected_edge_match': graph_metrics['expected_edge_match'],
        'duplicate_replay_inflation_rate': graph_metrics[
            'duplicate_replay_inflation_rate'
        ] == 0,
        'deterministic_replay_byte_match': graph_metrics[
            'deterministic_replay_byte_match'
        ],
        'malformed_and_write_survival': failure_metrics['survival_rate'] == 1.0,
        'policy_lineage_preservation': graph_metrics[
            'policy_lineage_preservation'
        ] == 1.0,
        'behavior_delta': not behavior_metrics['behavior_delta'],
        'prompt_delta': not behavior_metrics['prompt_delta'],
        'retrieval_count': behavior_metrics['retrieval_count'] == 0,
        'provider_network_count': behavior_metrics[
            'external_provider_network_count'
        ] == 0,
        'disabled_graph_absent': behavior_metrics['disabled_graph_absent'],
    }
    automatic_decision = 'PASS' if all(automatic_gates.values()) else 'FAIL'
    decision = (
        'INCONCLUSIVE_PENDING_HUMAN_REVIEW'
        if automatic_decision == 'PASS'
        else 'FAIL'
    )
    report = {
        'schema_version': 1,
        'benchmark': BENCHMARK,
        'executed_at_utc': datetime.now(timezone.utc).isoformat(),
        'freeze_manifest_verified': True,
        'automatic_decision': automatic_decision,
        'decision': decision,
        'human_review_complete': False,
        'human_reviewed_extraction_precision': None,
        'graph_metrics': graph_metrics,
        'failure_metrics': failure_metrics,
        'behavior_metrics': behavior_metrics,
        'automatic_gates': automatic_gates,
        'authorization_boundary': preregistration['authorization_boundary'],
        'exit_claim_authorized': False,
        'production_readiness': False,
    }
    _write_json(output_directory / 'automatic-report.json', report)
    _write_json(output_directory / 'human-review.json', {
        'schema_version': 1,
        'benchmark': BENCHMARK,
        'instructions': _read_json(
            benchmark_directory / 'human-review-template.json'
        )['instructions'],
        'human_review_complete': False,
        'reviewer': None,
        'reviewed_at_utc': None,
        'entities': [
            {**item, 'supported': None, 'reviewer_notes': None}
            for item in extracted
        ],
    })
    return report


def produce_graph_evaluation_packet(
    benchmark_directory: str | Path,
    results_directory: str | Path,
    exchange_ids: list[str],
    output_path: str | Path,
) -> dict:
    benchmark_directory = Path(benchmark_directory)
    results_directory = Path(results_directory)
    output_path = Path(output_path)
    if verify_artifact_manifest(benchmark_directory / 'freeze-manifest.json') != 4:
        raise RuntimeError('graph evaluation freeze manifest is incomplete')
    automatic_report = _read_json(results_directory / 'automatic-report.json')
    if automatic_report.get('automatic_decision') != 'PASS':
        raise ValueError('automatic graph evaluation did not pass')
    if not exchange_ids or len(set(exchange_ids)) != len(exchange_ids):
        raise ValueError('exchange IDs must be non-empty and unique')

    corpus = _read_json(benchmark_directory / 'corpus.json')
    corpus_by_id = {
        exchange['exchange_id']: exchange
        for exchange in corpus['exchanges']
    }
    unknown = [item for item in exchange_ids if item not in corpus_by_id]
    if unknown:
        raise ValueError(f'unknown exchange ID: {unknown[0]}')

    graph = _read_json(results_directory / 'graph.json')
    packet_exchanges = []
    for exchange_id in exchange_ids:
        nodes = [
            node
            for node in graph['nodes'].values()
            if any(
                source['exchange_id'] == exchange_id
                for source in node['source_refs']
            )
        ]
        edges = [
            edge
            for edge in graph['edges'].values()
            if exchange_id in edge['source_exchange_ids']
        ]
        packet_exchanges.append({
            'exchange_id': exchange_id,
            'source': corpus_by_id[exchange_id],
            'entities': sorted(nodes, key=lambda item: item['node_id']),
            'edges': sorted(edges, key=lambda item: item['edge_id']),
            'policy_cases': [
                policy
                for policy in corpus['policy_cases']
                if policy['exchange_id'] == exchange_id
            ],
        })

    packet = {
        'schema_version': 1,
        'benchmark': BENCHMARK,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'developer_operator_source_linked_inspection',
        'human_judgments_included': False,
        'retrieval_authorized': False,
        'production_readiness': False,
        'exchanges': packet_exchanges,
    }
    _write_json(output_path, packet)
    return packet


def finalize_graph_memory_human_review(
    benchmark_directory: str | Path,
    results_directory: str | Path,
    human_review_path: str | Path,
) -> dict:
    benchmark_directory = Path(benchmark_directory)
    results_directory = Path(results_directory)
    human_review_path = Path(human_review_path)
    if verify_artifact_manifest(benchmark_directory / 'freeze-manifest.json') != 4:
        raise RuntimeError('graph evaluation freeze manifest is incomplete')

    automatic_report = _read_json(results_directory / 'automatic-report.json')
    review = _read_json(human_review_path)
    if automatic_report.get('automatic_decision') != 'PASS':
        raise ValueError('automatic graph evaluation did not pass')
    if review.get('benchmark') != BENCHMARK or review.get('schema_version') != 1:
        raise ValueError('human review contract mismatch')
    if review.get('human_review_complete') is not True:
        raise ValueError('human review is incomplete')
    if not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip():
        raise ValueError('human reviewer identity is required')
    reviewed_at = review.get('reviewed_at_utc')
    if not isinstance(reviewed_at, str) or not reviewed_at.endswith(('+00:00', 'Z')):
        raise ValueError('human review UTC timestamp is required')

    corpus = _read_json(benchmark_directory / 'corpus.json')
    labels = _read_json(benchmark_directory / 'expected-labels.json')
    with tempfile.TemporaryDirectory(prefix='joi-graph-review-') as temporary:
        _, _, expected_entities = _evaluate_graph(
            corpus,
            labels,
            Path(temporary),
        )

    immutable_fields = (
        'canonical_label',
        'entity_id',
        'entity_type',
        'exchange_id',
        'extractor_version',
        'policy_ids',
        'status',
        'surface_form',
        'turn_ids',
    )
    reviewed_entities = review.get('entities')
    if not isinstance(reviewed_entities, list) or len(reviewed_entities) != len(expected_entities):
        raise ValueError('human review entity count mismatch')
    expected_by_id = {item['entity_id']: item for item in expected_entities}
    supported_count = 0
    for entity in reviewed_entities:
        expected = expected_by_id.get(entity.get('entity_id'))
        if expected is None or any(entity.get(field) != expected.get(field) for field in immutable_fields):
            raise ValueError('human review entity identity mismatch')
        if not isinstance(entity.get('supported'), bool):
            raise ValueError('every human review judgment must be boolean')
        notes = entity.get('reviewer_notes')
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError('every human review judgment requires notes')
        supported_count += int(entity['supported'])

    precision = supported_count / len(reviewed_entities) if reviewed_entities else 0.0
    decision = 'PASS' if precision == 1.0 else 'FAIL'
    final_report = {
        **automatic_report,
        'finalized_at_utc': datetime.now(timezone.utc).isoformat(),
        'decision': decision,
        'human_review_complete': True,
        'human_reviewed_extraction_precision': precision,
        'human_reviewer': review['reviewer'],
        'human_reviewed_at_utc': reviewed_at,
        'exit_claim_authorized': decision == 'PASS',
        'production_readiness': False,
    }
    final_report['graph_metrics'] = {
        **automatic_report['graph_metrics'],
        'human_review_status': 'COMPLETE',
        'human_reviewed_extraction_precision': precision,
    }
    _write_json(results_directory / 'final-report.json', final_report)
    return final_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run the frozen offline Phase 5B graph write-only evaluation.',
    )
    parser.add_argument(
        '--benchmark-directory',
        default='docs/benchmarks/2026-09-01-graph-write-only',
    )
    parser.add_argument(
        '--output-directory',
        default='docs/benchmarks/2026-09-01-graph-write-only/results',
    )
    parser.add_argument('--finalize-human-review', action='store_true')
    parser.add_argument(
        '--human-review',
        default='docs/benchmarks/2026-09-01-graph-write-only/results/human-review.json',
    )
    parser.add_argument('--produce-exchange', action='append', default=[])
    parser.add_argument(
        '--inspection-output',
        default='docs/benchmarks/2026-09-01-graph-write-only/results/exchange-inspection.json',
    )
    args = parser.parse_args()
    if args.produce_exchange:
        packet = produce_graph_evaluation_packet(
            args.benchmark_directory,
            args.output_directory,
            args.produce_exchange,
            args.inspection_output,
        )
        print(json.dumps({
            'exchange_count': len(packet['exchanges']),
            'human_judgments_included': False,
        }, sort_keys=True))
        return
    if args.finalize_human_review:
        report = finalize_graph_memory_human_review(
            args.benchmark_directory,
            args.output_directory,
            args.human_review,
        )
        print(json.dumps({
            'decision': report['decision'],
            'exit_claim_authorized': report['exit_claim_authorized'],
        }, sort_keys=True))
        return
    report = run_graph_memory_benchmark(
        benchmark_directory=args.benchmark_directory,
        output_directory=args.output_directory,
    )
    print(json.dumps({
        'automatic_decision': report['automatic_decision'],
        'decision': report['decision'],
    }, sort_keys=True))


if __name__ == '__main__':
    main()