import io
import json

import pytest

from compact_memory_benchmark import DeterministicCompactCorpus
from compact_memory_reasoning_experiment import (
    FROZEN_DIAGNOSTIC_COMMIT,
    build_reasoning_off_payload,
    classify_model_outcome,
    consume_reasoning_off_stream,
    evaluate_candidate,
)
from memory.compact_memory import parse_model_candidate


def test_reasoning_off_payload_changes_only_the_reasoning_control():
    messages = [{'role': 'user', 'content': 'Return JSON.'}]

    payload = build_reasoning_off_payload('model', messages)

    assert payload == {
        'model': 'model',
        'messages': messages,
        'stream': True,
        'stream_options': {'include_usage': True},
        'reasoning_effort': 'none',
    }


def test_stream_records_first_token_content_json_and_zero_reasoning():
    events = b''.join((
        b'data: {"choices":[{"delta":{"content":"prefix "}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"{\\"claims\\":[]}"}}]}\n\n',
        b'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":5,"completion_tokens_details":{"reasoning_tokens":0}}}\n\n',
        b'data: [DONE]\n\n',
    ))
    clock = iter([1.1, 1.2, 1.4])

    result = consume_reasoning_off_stream(
        io.BytesIO(events),
        started_at=1.0,
        clock=lambda: next(clock),
    )

    assert result['time_to_first_token_seconds'] == pytest.approx(0.1)
    assert result['time_to_first_content_seconds'] == pytest.approx(0.2)
    assert result['time_to_first_json_content_seconds'] == pytest.approx(0.4)
    assert result['input_token_count'] == 12
    assert result['output_token_count'] == 5
    assert result['reasoning_token_count'] == 0
    assert result['reasoning_content'] == ''


def test_valid_candidate_metrics_cover_policy_and_compression():
    snapshot = DeterministicCompactCorpus().snapshot(25)
    corrected = next(turn for turn in snapshot.turns if turn.turn_id == 'user-18')
    candidate = parse_model_candidate(json.dumps({
        'summary_version': 1,
        'generated_at_utc': '2026-08-31T13:00:00+00:00',
        'summarizer': 'model-v1:test',
        'source_policy_revision': snapshot.policy_revision,
        'claims': [{
            'claim_id': 'claim-18',
            'text': corrected.content,
            'source_turn_ids': ['user-18'],
            'source_policy_ids': [corrected.source_policy_id],
            'confidence': 1.0,
            'status': 'explicit',
            'generated_at_utc': '2026-08-31T13:00:00+00:00',
            'summarizer': 'model-v1:test',
        }],
    }))

    metrics = evaluate_candidate(candidate, snapshot, max_source_characters=2000)

    assert metrics['provenance_coverage'] == 1.0
    assert metrics['correction_adherence'] == 1.0
    assert metrics['forgetting_adherence'] == 1.0
    assert 0 < metrics['factual_coverage'] < 1
    assert 0 < metrics['compression_ratio'] < 1


def test_outcome_taxonomy_distinguishes_starvation_and_mixed_causes():
    on_trials = [{'accepted': False, 'telemetry': {'time_to_first_json_content_seconds': None}}]
    successful_off = [{
        'accepted': True,
        'reasoning_control_verified': True,
        'resource_telemetry': {'available_ram_bytes_minimum': 2_000_000_000},
    }]
    failed_off = [{
        'accepted': False,
        'failure_class': 'model_timeout',
        'reasoning_control_verified': True,
        'resource_telemetry': {'available_ram_bytes_minimum': 100_000_000},
    }]

    assert classify_model_outcome(on_trials, successful_off) == 'reasoning-budget starvation'
    assert classify_model_outcome(on_trials, failed_off) == 'resource-pressure failure'


def test_outcome_taxonomy_marks_starvation_plus_malformed_as_mixed():
    on_trials = [{'accepted': False, 'telemetry': {'time_to_first_json_content_seconds': None}}]
    off_trials = [{
        'accepted': False,
        'malformed_output': True,
        'reasoning_control_verified': True,
        'telemetry': {'time_to_first_json_content_seconds': 1.0},
        'resource_telemetry': {'available_ram_bytes_minimum': 2_000_000_000},
    }]

    assert classify_model_outcome(on_trials, off_trials) == 'mixed cause'


def test_experiment_freezes_f9d8375_diagnostics():
    assert FROZEN_DIAGNOSTIC_COMMIT == 'f9d8375'