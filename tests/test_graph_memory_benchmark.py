import json
import shutil
from pathlib import Path

import pytest

from graph_memory_benchmark import (
    finalize_graph_memory_human_review,
    produce_graph_evaluation_packet,
    run_graph_memory_benchmark,
)
from memory.artifact_integrity import ArtifactIntegrityError


BENCHMARK_DIRECTORY = (
    Path(__file__).parents[1]
    / 'docs'
    / 'benchmarks'
    / '2026-09-01-graph-write-only'
)


def test_graph_benchmark_passes_automatic_gates_but_requires_human_review(
    tmp_path,
):
    report = run_graph_memory_benchmark(
        benchmark_directory=BENCHMARK_DIRECTORY,
        output_directory=tmp_path / 'results',
    )

    assert report['automatic_decision'] == 'PASS'
    assert report['decision'] == 'INCONCLUSIVE_PENDING_HUMAN_REVIEW'
    assert report['human_review_complete'] is False
    assert report['human_reviewed_extraction_precision'] is None
    assert report['exit_claim_authorized'] is False
    assert all(report['automatic_gates'].values())
    assert report['graph_metrics']['automatic_extraction_precision'] == 1.0
    assert report['graph_metrics']['unsupported_entity_rate'] == 0
    assert report['graph_metrics']['source_provenance_coverage'] == 1.0
    assert report['graph_metrics']['duplicate_replay_inflation_rate'] == 0
    assert report['graph_metrics']['deterministic_replay_byte_match'] is True
    assert report['failure_metrics']['survival_rate'] == 1.0
    assert report['graph_metrics']['policy_lineage_preservation'] == 1.0


def test_graph_benchmark_measures_zero_behavior_prompt_and_read_delta(tmp_path):
    report = run_graph_memory_benchmark(
        benchmark_directory=BENCHMARK_DIRECTORY,
        output_directory=tmp_path / 'results',
    )
    behavior = report['behavior_metrics']

    assert behavior['behavior_delta'] is False
    assert behavior['prompt_delta'] is False
    assert behavior['retrieval_count'] == 0
    assert behavior['external_provider_network_count'] == 0
    assert behavior['disabled_graph_absent'] is True
    assert behavior['enabled_graph_written'] is True
    assert report['authorization_boundary']['retrieval_enabled'] is False
    assert report['authorization_boundary']['prompt_injection_enabled'] is False
    assert report['production_readiness'] is False


def test_graph_benchmark_refuses_tampered_frozen_corpus(tmp_path):
    frozen = tmp_path / 'frozen'
    shutil.copytree(BENCHMARK_DIRECTORY, frozen)
    corpus = frozen / 'corpus.json'
    corpus.write_text(
        corpus.read_text(encoding='utf-8') + ' ',
        encoding='utf-8',
    )

    with pytest.raises(ArtifactIntegrityError, match='mismatch'):
        run_graph_memory_benchmark(
            benchmark_directory=frozen,
            output_directory=tmp_path / 'results',
        )


def test_graph_benchmark_refuses_to_overwrite_frozen_inputs():
    with pytest.raises(RuntimeError, match='must not overwrite'):
        run_graph_memory_benchmark(
            benchmark_directory=BENCHMARK_DIRECTORY,
            output_directory=BENCHMARK_DIRECTORY,
        )


def _completed_review(results_directory: Path, reviewer='independent-reviewer') -> Path:
    review_path = results_directory / 'human-review.json'
    review = json.loads(review_path.read_text(encoding='utf-8'))
    review['human_review_complete'] = True
    review['reviewer'] = reviewer
    review['reviewed_at_utc'] = '2026-09-02T12:00:00+00:00'
    for entity in review['entities']:
        entity['supported'] = True
        entity['reviewer_notes'] = 'Surface form is explicitly present in the cited source turn.'
    review_path.write_text(json.dumps(review, indent=2) + '\n', encoding='utf-8')
    return review_path


def test_finalize_graph_review_authorizes_bounded_exit_claim(tmp_path):
    results = tmp_path / 'results'
    run_graph_memory_benchmark(
        benchmark_directory=BENCHMARK_DIRECTORY,
        output_directory=results,
    )
    review_path = _completed_review(results)

    final = finalize_graph_memory_human_review(
        benchmark_directory=BENCHMARK_DIRECTORY,
        results_directory=results,
        human_review_path=review_path,
    )

    assert final['decision'] == 'PASS'
    assert final['human_reviewed_extraction_precision'] == 1.0
    assert final['exit_claim_authorized'] is True
    assert final['authorization_boundary']['retrieval_enabled'] is False


def test_finalize_graph_review_refuses_incomplete_or_tampered_review(tmp_path):
    results = tmp_path / 'results'
    run_graph_memory_benchmark(
        benchmark_directory=BENCHMARK_DIRECTORY,
        output_directory=results,
    )
    review_path = _completed_review(results)
    review = json.loads(review_path.read_text(encoding='utf-8'))
    review['entities'][0]['entity_id'] = 'tampered-id'
    review_path.write_text(json.dumps(review, indent=2) + '\n', encoding='utf-8')

    with pytest.raises(ValueError, match='identity mismatch'):
        finalize_graph_memory_human_review(
            BENCHMARK_DIRECTORY,
            results,
            review_path,
        )


def test_finalize_graph_review_fails_if_any_entity_is_unsupported(tmp_path):
    results = tmp_path / 'results'
    run_graph_memory_benchmark(
        benchmark_directory=BENCHMARK_DIRECTORY,
        output_directory=results,
    )
    review_path = _completed_review(results)
    review = json.loads(review_path.read_text(encoding='utf-8'))
    review['entities'][0]['supported'] = False
    review['entities'][0]['reviewer_notes'] = 'Not supported by the cited source.'
    review_path.write_text(json.dumps(review, indent=2) + '\n', encoding='utf-8')

    final = finalize_graph_memory_human_review(
        BENCHMARK_DIRECTORY,
        results,
        review_path,
    )

    assert final['decision'] == 'FAIL'
    assert final['human_reviewed_extraction_precision'] == 0.9
    assert final['exit_claim_authorized'] is False


def test_graph_benchmark_refuses_to_overwrite_completed_human_review(tmp_path):
    results = tmp_path / 'results'
    run_graph_memory_benchmark(
        benchmark_directory=BENCHMARK_DIRECTORY,
        output_directory=results,
    )
    review_path = _completed_review(results)
    before = review_path.read_bytes()

    with pytest.raises(RuntimeError, match='completed human review'):
        run_graph_memory_benchmark(
            benchmark_directory=BENCHMARK_DIRECTORY,
            output_directory=results,
        )

    assert review_path.read_bytes() == before


def test_produce_graph_evaluation_packet_for_entity_exchanges(tmp_path):
    results = tmp_path / 'results'
    run_graph_memory_benchmark(
        benchmark_directory=BENCHMARK_DIRECTORY,
        output_directory=results,
    )
    exchange_ids = [
        'graph-eval-001',
        'graph-eval-002',
        'graph-eval-003',
        'graph-eval-004',
        'graph-eval-007',
        'graph-eval-008',
    ]

    packet = produce_graph_evaluation_packet(
        benchmark_directory=BENCHMARK_DIRECTORY,
        results_directory=results,
        exchange_ids=exchange_ids,
        output_path=results / 'exchange-inspection.json',
    )

    assert [item['exchange_id'] for item in packet['exchanges']] == exchange_ids
    assert [len(item['entities']) for item in packet['exchanges']] == [2, 2, 2, 1, 2, 1]
    assert [len(item['edges']) for item in packet['exchanges']] == [1, 1, 1, 0, 1, 0]
    assert packet['human_judgments_included'] is False
    assert packet['retrieval_authorized'] is False
    assert packet['exchanges'][0]['source']['user'] == (
        'My name is Luna. I prefer green tea.'
    )
    assert (results / 'exchange-inspection.json').exists()


def test_produce_graph_evaluation_packet_refuses_unknown_exchange(tmp_path):
    results = tmp_path / 'results'
    run_graph_memory_benchmark(
        benchmark_directory=BENCHMARK_DIRECTORY,
        output_directory=results,
    )

    with pytest.raises(ValueError, match='unknown exchange ID'):
        produce_graph_evaluation_packet(
            BENCHMARK_DIRECTORY,
            results,
            ['graph-eval-999'],
            results / 'exchange-inspection.json',
        )