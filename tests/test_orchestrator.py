from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import core.orchestrator as orchestrator_module
from core.orchestrator import JoiOrchestrator


def _settings():
    return SimpleNamespace(
        app_name='JOI',
        lmstudio_base_url='http://localhost:1234/v1',
        local_model='model',
        request_timeout_seconds=10,
        voice_enabled=False,
        voice_mode='local',
        kokoro_python='kokoro-python',
        kokoro_model_path='model.onnx',
        kokoro_voices_path='voices.bin',
        tts_voice='af_heart',
        tts_language='en-us',
        tts_output_path='reply.wav',
        tts_timeout_seconds=30,
        elevenlabs_api_key='',
        elevenlabs_voice_id='',
        elevenlabs_model_id='eleven_multilingual_v2',
        elevenlabs_base_url='https://api.elevenlabs.io/v1',
        elevenlabs_timeout_seconds=15,
        vision_enabled=False,
        cloud_enabled=False,
        memory_mode='session',
        persistent_memory_enabled=False,
        memory_store_path='episodic.sqlite3',
        compact_memory_enabled=False,
        compact_memory_path='compact-memory.json',
        compact_memory_max_characters=2000,
        model_compact_memory_enabled=False,
        model_compact_memory_path='compact-memory-model-candidate.json',
        compact_memory_evaluation_path='compact-memory-evaluation.json',
        compact_memory_provider='local',
        openai_api_key='',
        openai_model='gpt-5.6-luna',
        openai_base_url='https://api.openai.com/v1',
        openai_timeout_seconds=60,
    )


def test_chat_records_successful_exchange(monkeypatch):
    brain = Mock()
    brain.chat.return_value = 'Hello'
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    joi = JoiOrchestrator(_settings(), 'system', Mock())

    assert joi.chat('Hi') == 'Hello'
    assert joi.memory.snapshot()[-2:] == [
        {'role': 'user', 'content': 'Hi'},
        {'role': 'assistant', 'content': 'Hello'},
    ]


def test_chat_rolls_back_and_logs_brain_failure(monkeypatch):
    brain = Mock()
    brain.chat.side_effect = RuntimeError('offline')
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    logger = Mock()
    joi = JoiOrchestrator(_settings(), 'system', logger)

    with pytest.raises(RuntimeError, match='offline'):
        joi.chat('Hi')

    assert joi.memory.snapshot() == [{'role': 'system', 'content': 'system'}]
    logger.exception.assert_called_once_with('Brain request failed')


def test_chat_failure_restores_history_at_memory_limit(monkeypatch):
    brain = Mock()
    brain.chat.side_effect = RuntimeError('offline')
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    joi = JoiOrchestrator(_settings(), 'system', Mock())
    for turn in range(20):
        joi.memory.add_user(f'question {turn}')
        joi.memory.add_assistant(f'answer {turn}')
    history_before_request = joi.memory.snapshot()

    with pytest.raises(RuntimeError, match='offline'):
        joi.chat('This request fails')

    assert joi.memory.snapshot() == history_before_request


def test_enabled_voice_uses_configured_kokoro_router(monkeypatch, tmp_path):
    settings = _settings()
    settings.voice_enabled = True
    settings.kokoro_python = 'kokoro-python'
    settings.kokoro_model_path = 'model.onnx'
    settings.kokoro_voices_path = 'voices.bin'
    settings.tts_voice = 'af_heart'
    settings.tts_language = 'en-us'
    settings.tts_output_path = str(tmp_path / 'reply.wav')
    settings.tts_timeout_seconds = 30
    voice = Mock()
    voice_router = Mock(return_value=voice)
    monkeypatch.setattr(orchestrator_module, 'KokoroVoiceRouter', voice_router)

    joi = JoiOrchestrator(settings, 'system', Mock())
    result = joi.speak('Hello')

    voice_router.assert_called_once_with(
        python_executable='kokoro-python',
        model_path='model.onnx',
        voices_path='voices.bin',
        voice='af_heart',
        language='en-us',
        output_path=str(tmp_path / 'reply.wav'),
        timeout_seconds=30,
    )
    voice.speak.assert_called_once_with('Hello')
    assert result == voice.speak.return_value


def test_hybrid_voice_fallback_preserves_session(monkeypatch, tmp_path):
    settings = _settings()
    settings.voice_enabled = True
    settings.voice_mode = 'hybrid'
    settings.cloud_enabled = True
    settings.elevenlabs_api_key = 'local-secret'
    settings.elevenlabs_voice_id = 'voice-id'
    settings.tts_output_path = str(tmp_path / 'reply.wav')
    local_voice = Mock()
    local_voice.speak.return_value = tmp_path / 'reply.wav'
    online_voice = Mock()
    online_voice.speak.side_effect = RuntimeError('provider unavailable')
    monkeypatch.setattr(orchestrator_module, 'KokoroVoiceRouter', Mock(return_value=local_voice))
    monkeypatch.setattr(
        orchestrator_module,
        'ElevenLabsVoiceProvider',
        Mock(return_value=online_voice),
    )
    logger = Mock()
    joi = JoiOrchestrator(settings, 'system', logger)
    joi.memory.add_user('Keep this')
    joi.memory.add_assistant('I will')
    memory_before_speech = joi.memory.snapshot()

    result = joi.speak('Hello')

    online_voice.speak.assert_called_once_with('Hello')
    local_voice.speak.assert_called_once_with('Hello')
    assert result == tmp_path / 'reply.wav'
    assert joi.memory.snapshot() == memory_before_speech


def test_memory_off_does_not_retain_chat_exchange(monkeypatch):
    brain = Mock()
    brain.chat.return_value = 'Private reply'
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    joi = JoiOrchestrator(_settings(), 'system', Mock())

    joi.set_runtime_state('memory', 'off')

    assert joi.chat('Private question') == 'Private reply'
    assert joi.memory.snapshot() == [{'role': 'system', 'content': 'system'}]
    brain.chat.assert_called_once_with([
        {'role': 'system', 'content': 'system'},
        {'role': 'user', 'content': 'Private question'},
    ])


def test_runtime_state_refuses_unconfigured_capability(monkeypatch):
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock())
    joi = JoiOrchestrator(_settings(), 'system', Mock())

    with pytest.raises(ValueError, match='MIC is not configured'):
        joi.set_runtime_state('mic', 'on')

    assert joi.state.mic_enabled is False


def test_cloud_off_routes_hybrid_voice_locally(monkeypatch):
    settings = _settings()
    settings.voice_enabled = True
    settings.voice_mode = 'hybrid'
    settings.cloud_enabled = True
    settings.elevenlabs_api_key = 'local-secret'
    settings.elevenlabs_voice_id = 'voice-id'
    local_voice = Mock()
    online_voice = Mock()
    monkeypatch.setattr(orchestrator_module, 'KokoroVoiceRouter', Mock(return_value=local_voice))
    monkeypatch.setattr(
        orchestrator_module,
        'ElevenLabsVoiceProvider',
        Mock(return_value=online_voice),
    )
    joi = JoiOrchestrator(settings, 'system', Mock())

    joi.set_runtime_state('cloud', 'off')
    joi.speak('Keep this local')

    local_voice.speak.assert_called_once_with('Keep this local')
    online_voice.speak.assert_not_called()
    assert joi.status()['cloud'] == 'OFF'
    assert joi.status()['voice'] == 'ON (LOCAL)'


def test_cloud_off_disables_online_only_voice(monkeypatch):
    settings = _settings()
    settings.voice_enabled = True
    settings.voice_mode = 'online'
    settings.cloud_enabled = True
    settings.elevenlabs_api_key = 'local-secret'
    settings.elevenlabs_voice_id = 'voice-id'
    online_voice = Mock()
    monkeypatch.setattr(
        orchestrator_module,
        'ElevenLabsVoiceProvider',
        Mock(return_value=online_voice),
    )
    joi = JoiOrchestrator(settings, 'system', Mock())

    joi.set_runtime_state('cloud', 'off')

    assert joi.speak('Do not send this') is None
    online_voice.speak.assert_not_called()
    assert joi.status()['voice'] == 'DISABLED'


def test_successful_persistent_chat_writes_complete_exchange(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    brain = Mock()
    brain.chat.return_value = 'Durable reply'
    store = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    memory_store = Mock(return_value=store)
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', memory_store)
    joi = JoiOrchestrator(settings, 'system', Mock())

    assert joi.chat('Remember this') == 'Durable reply'

    memory_store.assert_called_once_with('episodic.sqlite3')
    store.append_exchange.assert_called_once_with('Remember this', 'Durable reply')


def test_persistent_write_failure_does_not_block_chat(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    brain = Mock()
    brain.chat.return_value = 'Reply survives'
    store = Mock()
    store.append_exchange.side_effect = RuntimeError('disk unavailable')
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    logger = Mock()
    joi = JoiOrchestrator(settings, 'system', logger)

    assert joi.chat('Hello') == 'Reply survives'
    assert joi.chat('Still working') == 'Reply survives'
    assert joi.memory.snapshot()[-1] == {'role': 'assistant', 'content': 'Reply survives'}
    store.append_exchange.assert_called_once_with('Hello', 'Reply survives')
    logger.exception.assert_called_once_with('Persistent memory write failed')


def test_failed_brain_request_is_not_persisted(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    brain = Mock()
    brain.chat.side_effect = RuntimeError('offline')
    store = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    joi = JoiOrchestrator(settings, 'system', Mock())

    with pytest.raises(RuntimeError, match='offline'):
        joi.chat('Do not store this')

    store.append_exchange.assert_not_called()


def test_persistent_store_initialization_failure_degrades_to_live_chat(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    brain = Mock()
    brain.chat.return_value = 'Still available'
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(
        orchestrator_module,
        'EpisodicMemoryStore',
        Mock(side_effect=RuntimeError('corrupted store')),
    )
    logger = Mock()

    joi = JoiOrchestrator(settings, 'system', logger)

    assert joi.chat('Hello') == 'Still available'
    assert joi.status()['memory'] == 'PERSISTENT (UNAVAILABLE)'
    logger.exception.assert_called_once_with('Persistent memory initialization failed')


def test_memory_off_prevents_persistent_write(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    brain = Mock()
    brain.chat.return_value = 'Private reply'
    store = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    joi = JoiOrchestrator(settings, 'system', Mock())

    joi.set_runtime_state('memory', 'off')

    assert joi.chat('Private question') == 'Private reply'
    store.append_exchange.assert_not_called()


def test_compact_memory_receives_persisted_turns_without_prompt_injection(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    settings.compact_memory_enabled = True
    brain = Mock()
    brain.chat.return_value = 'Live reply'
    turns = [Mock(turn_id='user-1'), Mock(turn_id='assistant-1')]
    store = Mock()
    store.append_exchange.return_value = turns
    worker = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryManager', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryWorker', Mock(return_value=worker))
    joi = JoiOrchestrator(settings, 'system', Mock())

    assert joi.chat('Live question') == 'Live reply'

    worker.submit.assert_called_once_with(turns)
    brain.chat.assert_called_once_with([
        {'role': 'system', 'content': 'system'},
        {'role': 'user', 'content': 'Live question'},
    ])


def test_compact_memory_does_not_run_when_persistent_write_fails(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    settings.compact_memory_enabled = True
    brain = Mock()
    brain.chat.return_value = 'Live reply'
    store = Mock()
    store.append_exchange.side_effect = RuntimeError('disk unavailable')
    worker = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryManager', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryWorker', Mock(return_value=worker))
    joi = JoiOrchestrator(settings, 'system', Mock())

    assert joi.chat('Live question') == 'Live reply'

    worker.submit.assert_not_called()


def test_corrupted_compact_memory_does_not_block_chat_or_episodic_write(
    monkeypatch,
    tmp_path,
):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    settings.compact_memory_enabled = True
    settings.compact_memory_path = str(tmp_path / 'compact-memory.json')
    (tmp_path / 'compact-memory.json').write_text('{broken', encoding='utf-8')
    brain = Mock()
    brain.chat.return_value = 'Live reply'
    store = Mock()
    store.append_exchange.return_value = [Mock(), Mock()]
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    logger = Mock()
    joi = JoiOrchestrator(settings, 'system', logger)

    assert joi.chat('Live question') == 'Live reply'

    store.append_exchange.assert_called_once_with('Live question', 'Live reply')
    assert joi.compact_memory_worker is None
    logger.exception.assert_called_once_with('Compact memory initialization failed')


def test_disabled_compact_memory_constructs_no_shadow_components(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    brain = Mock()
    brain.chat.return_value = 'Live reply'
    store = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    compact_store = Mock()
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryStore', compact_store)
    joi = JoiOrchestrator(settings, 'system', Mock())

    assert joi.chat('Live question') == 'Live reply'

    compact_store.assert_not_called()


def test_close_flushes_compact_memory_worker(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    settings.compact_memory_enabled = True
    worker = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock())
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryManager', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryWorker', Mock(return_value=worker))
    joi = JoiOrchestrator(settings, 'system', Mock())

    joi.close()

    worker.close.assert_called_once_with()


def test_memory_inspection_and_policy_commands_delegate_to_store(monkeypatch):
    settings = _settings()
    settings.persistent_memory_enabled = True
    store = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock())
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    joi = JoiOrchestrator(settings, 'system', Mock())

    assert joi.memory_store_status() == store.status.return_value
    assert joi.memory_recent(5) == store.inspect_recent.return_value
    assert joi.memory_why('turn-1') == store.inspect_turn.return_value
    assert joi.memory_correct('turn-1', 'Correct Value') == store.correct_turn.return_value
    assert joi.memory_forget('turn-1', 'User Request') == store.forget_turn.return_value
    store.inspect_recent.assert_called_once_with(limit=5)
    store.inspect_turn.assert_called_once_with('turn-1')
    store.correct_turn.assert_called_once_with(
        'turn-1',
        'Correct Value',
        reason='explicit user correction',
    )
    store.forget_turn.assert_called_once_with('turn-1', reason='User Request')


def test_memory_commands_refuse_unavailable_store(monkeypatch):
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock())
    joi = JoiOrchestrator(_settings(), 'system', Mock())

    with pytest.raises(ValueError, match='Persistent memory is not configured'):
        joi.memory_recent()


def test_model_compact_shadow_receives_effective_snapshot_after_exchange(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    settings.compact_memory_enabled = True
    settings.model_compact_memory_enabled = True
    brain = Mock()
    brain.chat.return_value = 'Live reply'
    snapshot = Mock(policy_revision=0)
    store = Mock()
    store.append_exchange.return_value = [Mock(), Mock()]
    store.effective_snapshot.return_value = snapshot
    extractive_worker = Mock()
    model_worker = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock(return_value=brain))
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryManager', Mock())
    monkeypatch.setattr(
        orchestrator_module,
        'CompactMemoryWorker',
        Mock(return_value=extractive_worker),
    )
    monkeypatch.setattr(
        orchestrator_module,
        'ModelCompactMemoryWorker',
        Mock(return_value=model_worker),
    )

    joi = JoiOrchestrator(settings, 'system', Mock())
    assert joi.chat('Live question') == 'Live reply'

    model_worker.submit.assert_called_once_with(snapshot)
    assert brain.chat.call_count == 1


def test_memory_policy_changes_trigger_model_compact_regeneration(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    settings.compact_memory_enabled = True
    settings.model_compact_memory_enabled = True
    snapshot = Mock(policy_revision=2)
    store = Mock()
    store.effective_snapshot.return_value = snapshot
    model_worker = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock())
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock(return_value=store))
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryManager', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryWorker', Mock())
    monkeypatch.setattr(
        orchestrator_module,
        'ModelCompactMemoryWorker',
        Mock(return_value=model_worker),
    )
    joi = JoiOrchestrator(settings, 'system', Mock())

    joi.memory_correct('turn-1', 'Corrected')
    joi.memory_forget('turn-2', 'User request')

    assert model_worker.submit.call_count == 2
    model_worker.submit.assert_called_with(snapshot)


def test_close_flushes_model_compact_memory_worker(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    settings.compact_memory_enabled = True
    settings.model_compact_memory_enabled = True
    model_worker = Mock()
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock())
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryManager', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryWorker', Mock())
    monkeypatch.setattr(
        orchestrator_module,
        'ModelCompactMemoryWorker',
        Mock(return_value=model_worker),
    )

    JoiOrchestrator(settings, 'system', Mock()).close()

    model_worker.close.assert_called_once_with()


def test_openai_compact_provider_uses_runtime_cloud_authorization(monkeypatch):
    settings = _settings()
    settings.memory_mode = 'persistent'
    settings.persistent_memory_enabled = True
    settings.compact_memory_enabled = True
    settings.model_compact_memory_enabled = True
    settings.compact_memory_provider = 'openai'
    settings.cloud_enabled = True
    settings.openai_api_key = 'sk-test-secret'
    provider = Mock()
    provider.provider_id = 'openai'
    provider.model_id = 'gpt-5.6-luna'
    provider_factory = Mock(return_value=provider)
    monkeypatch.setattr(orchestrator_module, 'OpenAICompactSummarizerProvider', provider_factory)
    monkeypatch.setattr(orchestrator_module, 'LocalLMStudioBrain', Mock())
    monkeypatch.setattr(orchestrator_module, 'EpisodicMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryStore', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryManager', Mock())
    monkeypatch.setattr(orchestrator_module, 'CompactMemoryWorker', Mock())
    monkeypatch.setattr(orchestrator_module, 'ModelCompactMemoryWorker', Mock())

    joi = JoiOrchestrator(settings, 'system', Mock())
    cloud_authorized = provider_factory.call_args.kwargs['cloud_authorized']

    assert cloud_authorized() is True
    joi.set_runtime_state('cloud', 'off')
    assert cloud_authorized() is False