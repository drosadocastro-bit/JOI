import argparse
import json
import os
import platform
import statistics
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from brain.local_llm import LocalLMStudioBrain
from config.settings import Settings
from memory.compact_memory import (
    CompactEvaluationStore,
    CompactMemoryEvaluator,
    ModelCompactMemoryManager,
    ModelCompactMemoryStore,
    ModelCompactSummarizer,
)
from memory.memory_store import EffectiveMemorySnapshot, EffectiveMemoryTurn


CORPUS_VERSION = 'compact-memory-deterministic-v1'
REQUIRED_CHECKPOINTS = (25, 50, 100, 200)
CORRECTIONS = {20: 18, 45: 43, 95: 93, 195: 193}
FORGETS = {24: 19, 49: 44, 99: 94, 199: 194}


class DeterministicCompactCorpus:
    version = CORPUS_VERSION

    def snapshot(self, update_count: int) -> EffectiveMemorySnapshot:
        if update_count < 1 or update_count > 200:
            raise ValueError('update_count must be between 1 and 200')
        turns = []
        policy_revision = 0
        for update in range(1, update_count + 1):
            timestamp = f'2026-08-31T12:{update // 60:02}:{update % 60:02}+00:00'
            turns.extend((
                EffectiveMemoryTurn(
                    turn_id=f'user-{update}',
                    exchange_id=f'exchange-{update}',
                    role='user',
                    content=f'Preference {update}: use option blue-{update}.',
                    source_policy_id=None,
                    forgotten=False,
                    completed_exchange=True,
                    created_at_utc=timestamp,
                ),
                EffectiveMemoryTurn(
                    turn_id=f'assistant-{update}',
                    exchange_id=f'exchange-{update}',
                    role='assistant',
                    content=f'Acknowledged preference {update}.',
                    source_policy_id=None,
                    forgotten=False,
                    completed_exchange=True,
                    created_at_utc=timestamp,
                ),
            ))
            if update in CORRECTIONS:
                target = CORRECTIONS[update]
                policy_revision += 1
                self._replace_turn(
                    turns,
                    f'user-{target}',
                    content=f'Preference {target} corrected: use option green-{target}.',
                    source_policy_id=f'policy-correct-{update}',
                )
            if update in FORGETS:
                target = FORGETS[update]
                policy_revision += 1
                self._replace_turn(
                    turns,
                    f'user-{target}',
                    content=None,
                    source_policy_id=f'policy-forget-{update}',
                    forgotten=True,
                )
        return EffectiveMemorySnapshot(policy_revision, tuple(turns))

    @staticmethod
    def _replace_turn(turns, turn_id, **changes):
        for index, turn in enumerate(turns):
            if turn.turn_id == turn_id:
                turns[index] = replace(turn, **changes)
                return
        raise RuntimeError(f'benchmark corpus turn not found: {turn_id}')


def percentile(values, fraction):
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def _artifact_bytes(path):
    return path.read_bytes() if path.exists() else None


def _checkpoint_metrics(update_count, reports):
    latest = reports[-1]
    latencies = [latest.latency_seconds]
    baseline_corrected_ids = {
        item['source_turn_ids'][0]
        for item in latest.baseline_output
        if item['source_policy_ids'][0]
        and item['source_policy_ids'][0].startswith('policy-correct-')
    }
    candidate_source_ids = {
        turn_id
        for claim in latest.candidate_output
        for turn_id in claim['source_turn_ids']
    }
    correction_adherence = (
        len(baseline_corrected_ids & candidate_source_ids) / len(baseline_corrected_ids)
        if baseline_corrected_ids else 1.0
    )
    return {
        'update_count': update_count,
        'extractive_claim_count': latest.baseline_claim_count,
        'model_backed_claim_count': latest.candidate_claim_count,
        'factual_coverage': latest.factual_coverage,
        'unsupported_factual_claims': latest.unsupported_claim_count,
        'provenance_coverage': latest.provenance_coverage,
        'correction_adherence': correction_adherence,
        'forgetting_adherence': latest.forgetting_adherence,
        'compression_ratio': latest.compression_ratio,
        'output_size_bytes': latest.storage_bytes,
        'average_summarization_latency_seconds': statistics.mean(latencies),
        'p95_summarization_latency_seconds': percentile(latencies, 0.95),
        'failed_or_malformed_candidate_count': int(not latest.accepted),
    }


def _hard_failure(report, snapshot, candidate_path, previous_bytes):
    current_bytes = _artifact_bytes(candidate_path)
    if not report.accepted:
        if current_bytes != previous_bytes:
            return 'rejected candidate changed the previous valid Compact Memory'
        return None
    forgotten_ids = {turn.turn_id for turn in snapshot.turns if turn.forgotten}
    current = json.loads(current_bytes.decode('utf-8'))
    source_ids = {
        turn_id
        for claim in current['claims']
        for turn_id in claim['source_turn_ids']
    }
    if forgotten_ids & source_ids:
        return 'logically forgotten claim was resurrected'
    if report.provenance_coverage < 1.0:
        return 'durable factual claim lacks valid provenance'
    if report.unsupported_claim_count:
        return 'unsupported factual claim was accepted'
    if report.stale_claim_rate:
        return 'superseded claim was treated as current'
    return None


def run_benchmark(
    settings,
    output_directory: str | Path,
    checkpoints=REQUIRED_CHECKPOINTS,
    brain=None,
    progress=None,
    request_timeout_seconds=None,
):
    checkpoints = tuple(checkpoints)
    if not checkpoints or tuple(sorted(set(checkpoints))) != checkpoints:
        raise ValueError('checkpoints must be unique and increasing')
    if checkpoints[-1] > 200:
        raise ValueError('the deterministic corpus supports at most 200 updates')
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    candidate_path = output_directory / 'model-candidate.json'
    update_report_path = output_directory / 'update-reports.json'
    actual_timeout = request_timeout_seconds or settings.request_timeout_seconds
    brain = brain or LocalLMStudioBrain(
        settings.lmstudio_base_url,
        settings.local_model,
        actual_timeout,
    )
    health = brain.health()
    reports = []
    hard_failures = []
    completed_updates = 0
    checkpoint_results = []

    if health.get('ok') and health.get('selected_model_visible'):
        manager = ModelCompactMemoryManager(
            ModelCompactMemoryStore(candidate_path),
            ModelCompactSummarizer(brain, settings.local_model),
        )
        evaluator = CompactMemoryEvaluator(
            manager,
            CompactEvaluationStore(update_report_path),
            max_source_characters=settings.compact_memory_max_characters,
        )
        corpus = DeterministicCompactCorpus()
        for update in checkpoints:
            snapshot = corpus.snapshot(update)
            previous_bytes = _artifact_bytes(candidate_path)
            report = evaluator.update(
                snapshot,
                checkpoint=update if update in checkpoints else None,
            )
            reports.append(report)
            completed_updates = update
            failure = _hard_failure(report, snapshot, candidate_path, previous_bytes)
            if progress is not None:
                progress(update, report)
            if failure is not None:
                hard_failures.append({'update': update, 'reason': failure})
                break
            checkpoint_results.append(_checkpoint_metrics(update, reports))

    model_available = bool(
        health.get('ok') and health.get('selected_model_visible')
    )
    failed_candidates = sum(not report.accepted for report in reports)
    if hard_failures or (completed_updates == checkpoints[-1] and failed_candidates):
        recommendation = 'FAIL'
    elif completed_updates == checkpoints[-1] and len(checkpoint_results) == len(checkpoints):
        recommendation = 'PASS'
    else:
        recommendation = 'INCONCLUSIVE'
    result = {
        'schema_version': 1,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'environment': {
            'operating_system': platform.platform(),
            'python_version': platform.python_version(),
            'processor': os.environ.get('PROCESSOR_IDENTIFIER') or platform.processor(),
        },
        'model': {
            'identifier': settings.local_model,
            'endpoint': settings.lmstudio_base_url,
            'visible': bool(health.get('selected_model_visible')),
            'request_timeout_seconds': actual_timeout,
            'generation_parameters': 'LM Studio API defaults; stream=false',
        },
        'corpus': {
            'identifier': 'joi-compact-memory-deterministic',
            'version': CORPUS_VERSION,
            'requested_checkpoints': list(checkpoints),
            'completed_updates': completed_updates,
            'execution_mode': 'independent cumulative checkpoint snapshots',
            'trials_per_checkpoint': 1,
            'max_source_characters': settings.compact_memory_max_characters,
        },
        'checkpoints': checkpoint_results,
        'candidate_failures': [
            {'update': report.checkpoint, 'reason': report.rejection_reason}
            for report in reports
            if not report.accepted
        ],
        'hard_failures': hard_failures,
        'model_available': model_available,
        'recommendation': recommendation,
        'live_prompt_injection_enabled': False,
        'human_review_complete': False,
    }
    _write_artifacts(output_directory, result)
    return result


def _write_artifacts(output_directory, result):
    json_path = output_directory / 'compact-memory-benchmark.json'
    markdown_path = output_directory / 'compact-memory-benchmark.md'
    json_path.write_text(
        json.dumps(result, ensure_ascii=True, indent=2) + '\n',
        encoding='utf-8',
    )
    rows = [
        '| Updates | Extractive | Model | Coverage | Unsupported | Provenance | '
        'Correction | Forgetting | Compression | Bytes | Avg latency | P95 latency | Failures |',
        '| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for item in result['checkpoints']:
        rows.append(
            f"| {item['update_count']} | {item['extractive_claim_count']} | "
            f"{item['model_backed_claim_count']} | {item['factual_coverage']:.3f} | "
            f"{item['unsupported_factual_claims']} | {item['provenance_coverage']:.3f} | "
            f"{item['correction_adherence']:.3f} | {item['forgetting_adherence']:.3f} | "
            f"{item['compression_ratio']:.3f} | {item['output_size_bytes']} | "
            f"{item['average_summarization_latency_seconds']:.3f}s | "
            f"{item['p95_summarization_latency_seconds']:.3f}s | "
            f"{item['failed_or_malformed_candidate_count']} |"
        )
    markdown = '\n'.join([
        '# Compact Memory Real-Model Benchmark',
        '',
        f"**Recommendation: {result['recommendation']}**",
        '',
        f"- Generated: {result['generated_at_utc']}",
        f"- Environment: {result['environment']['operating_system']}",
        f"- Python: {result['environment']['python_version']}",
        f"- Model: `{result['model']['identifier']}`",
        f"- Endpoint: `{result['model']['endpoint']}`",
        f"- Parameters: {result['model']['generation_parameters']}",
        f"- Request timeout: {result['model']['request_timeout_seconds']} seconds",
        f"- Corpus: `{result['corpus']['identifier']}@{result['corpus']['version']}`",
        f"- Completed updates: {result['corpus']['completed_updates']}",
        f"- Execution: {result['corpus']['execution_mode']}",
        f"- Trials per checkpoint: {result['corpus']['trials_per_checkpoint']}",
        f"- Maximum source characters: {result['corpus']['max_source_characters']}",
        '- Live prompt injection: disabled',
        '- Human review: incomplete',
        '',
        '## Checkpoints',
        '',
        *rows,
        '',
        'Average and P95 latency are identical because this run used one real-model '
        'trial per cumulative checkpoint.',
        '',
        '## Extractive Vs Model',
        '',
        (
            f"At the final checkpoint, the extractive baseline retained "
            f"{result['checkpoints'][-1]['extractive_claim_count']} claims while "
            f"the model-backed candidate retained "
            f"{result['checkpoints'][-1]['model_backed_claim_count']}. "
            f"Model factual coverage was "
            f"{result['checkpoints'][-1]['factual_coverage']:.3f}."
            if result['checkpoints'] else
            'No checkpoint comparison was available.'
        ),
        '',
        '## Failures',
        '',
        f"- Candidate failures: {len(result['candidate_failures'])}",
        f"- Hard failures: {len(result['hard_failures'])}",
        '',
        'Phase 5A remains shadow-only until human review is complete.',
        '',
    ])
    markdown_path.write_text(markdown, encoding='utf-8')


def rebuild_artifacts(output_directory: str | Path):
    output_directory = Path(output_directory)
    result_path = output_directory / 'compact-memory-benchmark.json'
    if not result_path.exists():
        raise RuntimeError('benchmark summary does not exist')
    result = json.loads(result_path.read_text(encoding='utf-8'))
    result['corpus'].setdefault('trials_per_checkpoint', 1)
    reports = CompactEvaluationStore(
        output_directory / 'update-reports.json'
    ).load()
    result['checkpoints'] = [
        _checkpoint_metrics(report.checkpoint, reports[:index])
        for index, report in enumerate(reports, start=1)
    ]
    result['candidate_failures'] = [
        {'update': report.checkpoint, 'reason': report.rejection_reason}
        for report in reports
        if not report.accepted
    ]
    _write_artifacts(output_directory, result)
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Run the real-model Compact Memory shadow benchmark.',
    )
    parser.add_argument(
        '--output-directory',
        default='data/logs/compact-memory-benchmark',
    )
    parser.add_argument(
        '--request-timeout-seconds',
        type=int,
        default=None,
        help='Benchmark-only model request timeout; defaults to configured timeout.',
    )
    parser.add_argument(
        '--rebuild-from-update-reports',
        action='store_true',
        help='Regenerate summary artifacts without running model inference.',
    )
    args = parser.parse_args()
    settings = Settings.load()

    if args.rebuild_from_update_reports:
        result = rebuild_artifacts(args.output_directory)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['recommendation'] == 'PASS' else 1)

    def print_progress(update, report):
        status = 'accepted' if report.accepted else f'rejected: {report.rejection_reason}'
        print(f'Update {update:03}: {report.latency_seconds:.3f}s - {status}', flush=True)

    result = run_benchmark(
        settings,
        args.output_directory,
        progress=print_progress,
        request_timeout_seconds=args.request_timeout_seconds,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['recommendation'] == 'PASS' else 1)


if __name__ == '__main__':
    main()