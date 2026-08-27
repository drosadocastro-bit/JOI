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
        vision_enabled=False,
        cloud_enabled=False,
        memory_mode='session',
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