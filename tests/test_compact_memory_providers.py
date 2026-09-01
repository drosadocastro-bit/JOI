import io
import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from brain.openai_compact_provider import OpenAICompactSummarizerProvider
from compact_memory_cloud_benchmark import run_cloud_benchmark
from memory.compact_memory import (
    CompactEvaluationStore,
    CompactMemoryError,
    CompactMemoryEvaluator,
    ModelCompactMemoryManager,
    ModelCompactMemoryStore,
    ModelCompactSummarizer,
    ProviderBackedCompactSummarizer,
    parse_model_candidate,
)
from memory.summarizer_provider import ProviderGeneration, SummarizerProviderError
from compact_memory_benchmark import DeterministicCompactCorpus


class FakeProvider:
    def __init__(self, provider_id, model_id, raw):
        self.provider_id = provider_id
        self.model_id = model_id
        self.raw = raw
        self.health_calls = 0
        self.generate_calls = 0

    def health(self):
        self.health_calls += 1
        return {
            'ok': True,
            'provider': self.provider_id,
            'model': self.model_id,
            'structured_outputs': True,
        }

    def generate(self, messages, schema):
        self.generate_calls += 1
        return ProviderGeneration(
            content=self.raw,
            provider=self.provider_id,
            model=self.model_id,
            total_latency_seconds=0.5,
            time_to_first_token_seconds=0.1,
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.000008,
        )


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode('utf-8')


def _candidate_payload(snapshot, model, summarizer):
    turn = next(
        item for item in snapshot.turns
        if not item.forgotten and item.content is not None
    )
    generated = '2026-08-31T18:00:00+00:00'
    return json.dumps({
        'summary_version': 1,
        'generated_at_utc': generated,
        'summarizer': summarizer,
        'source_policy_revision': snapshot.policy_revision,
        'claims': [{
            'claim_id': 'claim-1',
            'text': turn.content,
            'source_turn_ids': [turn.turn_id],
            'source_policy_ids': [turn.source_policy_id],
            'confidence': 1.0,
            'status': 'explicit',
            'generated_at_utc': generated,
            'summarizer': summarizer,
        }],
    })


def test_provider_backed_summarizer_health_checks_and_stamps_provenance():
    snapshot = DeterministicCompactCorpus().snapshot(25)
    version = 'model-v2:openai:gpt-5.6-luna'
    provider = FakeProvider(
        'openai',
        'gpt-5.6-luna',
        _candidate_payload(snapshot, 'gpt-5.6-luna', version),
    )

    candidate = ProviderBackedCompactSummarizer(provider)(snapshot)

    assert provider.health_calls == 1
    assert provider.generate_calls == 1
    assert candidate.provider == 'openai'
    assert candidate.model == 'gpt-5.6-luna'


def test_unhealthy_provider_is_not_executed():
    provider = FakeProvider('openai', 'gpt-5.6-luna', '{}')
    provider.health = Mock(return_value={'ok': False, 'error': 'unavailable'})

    with pytest.raises(SummarizerProviderError, match='provider unavailable'):
        ProviderBackedCompactSummarizer(provider)(
            DeterministicCompactCorpus().snapshot(25)
        )

    assert provider.generate_calls == 0


def test_openai_provider_refuses_cloud_off_without_opening_request():
    opener = Mock()
    provider = OpenAICompactSummarizerProvider(
        api_key='sk-test-secret',
        model='gpt-5.6-luna',
        cloud_authorized=lambda: False,
        opener=opener,
    )

    assert provider.health()['ok'] is False
    with pytest.raises(SummarizerProviderError, match='CLOUD is OFF'):
        provider.generate([], {'type': 'object'})
    opener.assert_not_called()


def test_openai_provider_redacts_key_from_http_error():
    secret = 'sk-test-secret-value'

    def failing_opener(request, timeout):
        raise RuntimeError(f'authorization failed for {secret}')

    provider = OpenAICompactSummarizerProvider(
        api_key=secret,
        model='gpt-5.6-luna',
        cloud_authorized=lambda: True,
        opener=failing_opener,
    )

    with pytest.raises(SummarizerProviderError) as error:
        provider.health()

    assert secret not in str(error.value)
    assert '[REDACTED]' in str(error.value)


def test_openai_provider_reload_replaces_key_without_restart():
    authorization_headers = []

    def opener(request, timeout):
        authorization_headers.append(request.get_header('Authorization'))
        return FakeResponse({'id': 'gpt-5.6-luna'})

    provider = OpenAICompactSummarizerProvider(
        api_key='sk-test-revoked',
        model='gpt-5.6-luna',
        cloud_authorized=lambda: True,
        opener=opener,
    )

    assert provider.health()['ok'] is True
    provider.reload_api_key('sk-test-replacement')
    assert provider.health()['ok'] is True

    assert authorization_headers == [
        'Bearer sk-test-revoked',
        'Bearer sk-test-replacement',
    ]


def test_openai_provider_reload_missing_key_fails_closed():
    opener = Mock(return_value=FakeResponse({'id': 'gpt-5.6-luna'}))
    provider = OpenAICompactSummarizerProvider(
        api_key='sk-test-current',
        model='gpt-5.6-luna',
        cloud_authorized=lambda: True,
        opener=opener,
    )

    provider.reload_api_key('')

    assert provider.health() == {
        'ok': False,
        'error': 'OPENAI_API_KEY is not configured',
    }
    with pytest.raises(SummarizerProviderError, match='is not configured'):
        provider.generate([], {'type': 'object'})
    opener.assert_not_called()


def test_revoked_openai_key_is_rejected_without_fallback_or_secret_leak(caplog):
    revoked_key = 'sk-test-revoked-secret'
    opener = Mock(side_effect=RuntimeError(f'401 revoked: {revoked_key}'))
    provider = OpenAICompactSummarizerProvider(
        api_key=revoked_key,
        model='gpt-5.6-luna',
        cloud_authorized=lambda: True,
        opener=opener,
    )

    with pytest.raises(SummarizerProviderError) as error:
        provider.health()

    assert '401 revoked' in str(error.value)
    assert revoked_key not in str(error.value)
    assert revoked_key not in caplog.text
    assert '[REDACTED]' in str(error.value)
    assert opener.call_count == 1
    assert not hasattr(provider, 'fallback')


def test_revoked_key_rejects_update_without_memory_or_artifact_leak(tmp_path):
    revoked_key = 'sk-test-revoked-artifact-secret'
    provider = OpenAICompactSummarizerProvider(
        api_key=revoked_key,
        model='gpt-5.6-luna',
        cloud_authorized=lambda: True,
        opener=Mock(side_effect=RuntimeError(f'401 revoked: {revoked_key}')),
    )
    candidate_path = tmp_path / 'candidate.json'
    report_path = tmp_path / 'evaluation.json'
    manager = ModelCompactMemoryManager(
        ModelCompactMemoryStore(candidate_path),
        ProviderBackedCompactSummarizer(provider),
    )
    evaluator = CompactMemoryEvaluator(
        manager,
        CompactEvaluationStore(report_path),
    )

    report = evaluator.update(DeterministicCompactCorpus().snapshot(25), checkpoint=25)

    assert report.accepted is False
    assert report.rejection_reason == 'model summarizer failed'
    assert manager.state is None
    assert not candidate_path.exists()
    assert revoked_key not in report_path.read_text(encoding='utf-8')


def test_openai_provider_uses_strict_responses_schema_and_records_usage():
    captured = {}

    def opener(request, timeout):
        captured['request'] = request
        captured['timeout'] = timeout
        return FakeResponse({
            'status': 'completed',
            'output': [{
                'type': 'message',
                'content': [{'type': 'output_text', 'text': '{"claims": []}'}],
            }],
            'usage': {
                'input_tokens': 100,
                'output_tokens': 20,
                'input_tokens_details': {'cached_tokens': 25},
            },
        })

    provider = OpenAICompactSummarizerProvider(
        api_key='sk-test-secret',
        model='gpt-5.6-luna',
        cloud_authorized=lambda: True,
        timeout_seconds=17,
        opener=opener,
    )
    generation = provider.generate(
        [{'role': 'user', 'content': 'input'}],
        {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False},
    )
    body = json.loads(captured['request'].data.decode('utf-8'))

    assert body['model'] == 'gpt-5.6-luna'
    assert body['reasoning'] == {'effort': 'none'}
    assert body['text']['format']['strict'] is True
    assert captured['timeout'] == 17
    assert generation.input_tokens == 100
    assert generation.output_tokens == 20
    assert generation.time_to_first_token_seconds is None
    assert generation.estimated_cost_usd == pytest.approx(0.0000395)


def test_provider_switch_does_not_change_joi_state_or_memory():
    snapshot = DeterministicCompactCorpus().snapshot(25)
    state = {'cloud': True, 'memory_mode': 'persistent', 'active_brain': 'local'}
    state_before = dict(state)
    memory_before = json.dumps([asdict(turn) for turn in snapshot.turns], sort_keys=True)

    for provider_id, model_id in (
        ('local', 'nvidia/nemotron-3-nano'),
        ('openai', 'gpt-5.6-luna'),
        ('local', 'nvidia/nemotron-3-nano'),
    ):
        version = f'model-v2:{provider_id}:{model_id}'
        provider = FakeProvider(
            provider_id,
            model_id,
            _candidate_payload(snapshot, model_id, version),
        )
        ProviderBackedCompactSummarizer(provider)(snapshot)

    assert state == state_before
    assert json.dumps([asdict(turn) for turn in snapshot.turns], sort_keys=True) == memory_before


def test_provider_has_no_state_or_memory_ownership():
    provider = OpenAICompactSummarizerProvider(
        api_key='sk-test-secret',
        model='gpt-5.6-luna',
        cloud_authorized=lambda: True,
        opener=Mock(),
    )

    assert not ({'state', 'memory', 'memory_store', 'store'} & vars(provider).keys())


def test_provider_identity_mismatch_is_rejected():
    snapshot = DeterministicCompactCorpus().snapshot(25)
    version = 'model-v2:openai:gpt-5.6-luna'
    provider = FakeProvider(
        'openai',
        'gpt-5.6-luna',
        _candidate_payload(snapshot, 'gpt-5.6-luna', version),
    )
    original_generate = provider.generate

    def mismatched_generation(messages, schema):
        return SimpleNamespace(
            **{**asdict(original_generate(messages, schema)), 'model': 'other-model'}
        )

    provider.generate = mismatched_generation

    with pytest.raises(CompactMemoryError, match='provider identity mismatch'):
        ProviderBackedCompactSummarizer(provider)(snapshot)


def test_provider_failure_preserves_manager_state_and_store():
    previous = Mock()
    store = Mock()
    store.load.return_value = previous
    provider = FakeProvider('openai', 'gpt-5.6-luna', '{}')
    provider.generate = Mock(side_effect=SummarizerProviderError('provider failed'))
    manager = ModelCompactMemoryManager(
        store,
        ProviderBackedCompactSummarizer(provider),
    )

    with pytest.raises(CompactMemoryError, match='model summarizer failed'):
        manager.update(DeterministicCompactCorpus().snapshot(25))

    assert manager.state is previous
    store.save.assert_not_called()


def test_legacy_candidate_remains_readable_and_local_generation_adds_provenance():
    snapshot = DeterministicCompactCorpus().snapshot(25)
    version = 'model-v1:nvidia/nemotron-3-nano'
    raw = _candidate_payload(snapshot, 'nvidia/nemotron-3-nano', version)

    legacy = parse_model_candidate(raw)
    brain = Mock()
    brain.chat.return_value = raw
    generated = ModelCompactSummarizer(brain, 'nvidia/nemotron-3-nano')(snapshot)

    assert legacy.provider is None
    assert legacy.model is None
    assert generated.provider == 'local'
    assert generated.model == 'nvidia/nemotron-3-nano'


def test_cloud_benchmark_is_shadow_only_and_records_provider_telemetry(tmp_path):
    snapshot = DeterministicCompactCorpus().snapshot(25)
    version = 'model-v2:openai:gpt-5.6-luna'
    provider = FakeProvider(
        'openai',
        'gpt-5.6-luna',
        _candidate_payload(snapshot, 'gpt-5.6-luna', version),
    )
    settings = Mock(
        cloud_enabled=True,
        openai_api_key='sk-test-secret',
        openai_model='gpt-5.6-luna',
        openai_base_url='https://api.openai.com/v1',
        openai_timeout_seconds=60,
        compact_memory_max_characters=2000,
    )

    result = run_cloud_benchmark(
        settings,
        tmp_path,
        checkpoints=(25,),
        provider=provider,
    )

    assert result['publication_enabled'] is False
    assert result['provider']['identifier'] == 'openai'
    assert result['provider']['model'] == 'gpt-5.6-luna'
    assert result['checkpoints'][0]['input_tokens'] == 10
    assert result['checkpoints'][0]['output_tokens'] == 5
    assert result['checkpoints'][0]['estimated_cost_usd'] == 0.000008
    assert result['checkpoints'][0]['time_to_first_token_seconds'] == 0.1
    assert 'sk-test-secret' not in (tmp_path / 'cloud-benchmark.json').read_text(encoding='utf-8')