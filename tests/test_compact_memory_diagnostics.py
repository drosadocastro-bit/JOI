import io
import json
from types import SimpleNamespace

import pytest

from compact_memory_diagnostics import (
    FROZEN_CORPUS_VERSION,
    StreamTimeoutError,
    _capture_messages,
    classify_failure,
    collect_prompt_burden,
    consume_sse_stream,
    freeze_manifest,
    safe_raw_output,
)
from compact_memory_benchmark import DeterministicCompactCorpus


def test_diagnostics_use_frozen_corpus_contract():
    snapshot = DeterministicCompactCorpus().snapshot(200)

    assert FROZEN_CORPUS_VERSION == 'compact-memory-deterministic-v1'
    assert snapshot.policy_revision == 8
    assert len(snapshot.turns) == 400


def test_stream_parser_records_first_token_content_reasoning_and_usage():
    events = b''.join((
        b'data: {"choices":[{"delta":{"reasoning_content":"thinking"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"{\\"claims\\":"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"[]}"}}],"usage":{"prompt_tokens":10,"completion_tokens":4}}\n\n',
        b'data: [DONE]\n\n',
    ))
    clock = iter([10.2, 10.5])

    result = consume_sse_stream(io.BytesIO(events), started_at=10.0, clock=lambda: next(clock))

    assert result['time_to_first_token_seconds'] == pytest.approx(0.2)
    assert result['time_to_first_content_seconds'] == pytest.approx(0.5)
    assert result['content'] == '{"claims":[]}'
    assert result['reasoning_content'] == 'thinking'
    assert result['input_token_count'] == 10
    assert result['output_token_count'] == 4


def test_stream_timeout_preserves_partial_reasoning_telemetry():
    class TimeoutStream:
        fp = SimpleNamespace(raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=lambda value: None)))

        def __init__(self):
            self.calls = 0

        def readline(self):
            self.calls += 1
            if self.calls == 1:
                return b'data: {"choices":[{"delta":{"reasoning_content":"partial"}}]}\n'
            raise TimeoutError('timed out')

    clock = iter([10.1, 10.2, 10.3])

    with pytest.raises(StreamTimeoutError) as error:
        consume_sse_stream(
            TimeoutStream(),
            started_at=10.0,
            clock=lambda: next(clock),
            deadline=40.0,
        )

    assert error.value.telemetry['reasoning_content'] == 'partial'
    assert error.value.telemetry['time_to_first_token_seconds'] == pytest.approx(0.2)


def test_failure_taxonomy_is_explicit():
    assert classify_failure(timeout=True) == 'model_timeout'
    assert classify_failure(endpoint_available=False) == 'endpoint_or_model_unavailable'
    assert classify_failure(parse_error='bad json') == 'malformed_structured_output'
    assert classify_failure(validation_error='unsupported claim') == 'unsupported_claim_rejection'
    assert classify_failure(validation_error='claim source does not exist') == 'provenance_failure'
    assert classify_failure(validation_error='forgotten source') == 'forgetting_violation'
    assert classify_failure(validation_error='source policy is stale') == 'correction_violation'
    assert classify_failure(state_corrupted=True) == 'state_corruption'


def test_prompt_burden_counts_effective_policy_state():
    snapshot = DeterministicCompactCorpus().snapshot(25)

    burden = collect_prompt_burden(snapshot, max_source_characters=2000)

    assert burden['checkpoint_update_count'] == 25
    assert burden['candidate_fact_count'] == 49
    assert burden['correction_count'] == 1
    assert burden['forgotten_item_count'] == 1
    assert burden['effective_source_characters'] > 0
    assert burden['serialized_snapshot_bytes'] >= burden['effective_source_characters']


def test_capture_messages_uses_production_summarizer_prompt():
    snapshot = DeterministicCompactCorpus().snapshot(25)

    messages = _capture_messages(snapshot, 'diagnostic-model')

    assert messages[0]['role'] == 'system'
    assert 'Return JSON only' in messages[0]['content']
    assert json.loads(messages[1]['content'])['summarizer'] == 'model-v1:diagnostic-model'


def test_raw_output_is_bounded_and_control_characters_are_removed():
    raw = 'secret\x00value' + ('x' * 100)

    result = safe_raw_output(raw, max_characters=20)

    assert result == 'secretvaluexxxxxxxxx'
    assert len(result) == 20


def test_freeze_manifest_hashes_files_without_modifying_them(tmp_path):
    first = tmp_path / 'first.json'
    first.write_text('{"value": 1}\n', encoding='utf-8')

    manifest = freeze_manifest([first], commit='dedf2b8')

    assert manifest['commit'] == 'dedf2b8'
    assert manifest['files'][0]['path'].endswith('first.json')
    assert len(manifest['files'][0]['sha256']) == 64