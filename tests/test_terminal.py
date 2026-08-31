from types import SimpleNamespace
from unittest.mock import Mock

from memory.memory_store import EpisodicTurn, InspectedMemoryTurn, MemoryPolicyRecord
from interface.terminal import TerminalInterface


def test_terminal_prints_reply_before_reporting_voice_failure(monkeypatch, capsys):
    commands = iter(['hello', '/exit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(commands))
    joi = Mock()
    joi.state = SimpleNamespace(voice_enabled=True)
    joi.status.return_value = {
        'app_name': 'JOI',
        'brain': {'ok': True, 'selected_model': 'model'},
        'mic': 'OFF',
        'voice': 'ON (KOKORO)',
        'vision': 'OFF',
        'memory': 'SESSION',
        'cloud': 'OFF',
    }
    joi.chat.return_value = 'Hello there'
    joi.speak.side_effect = RuntimeError('speaker unavailable')

    TerminalInterface(joi).run()

    output = capsys.readouterr().out
    assert output.index('Joi > Hello there') < output.index('[VOICE ERROR] speaker unavailable')


def test_terminal_applies_runtime_state_command(monkeypatch, capsys):
    commands = iter(['/memory off', '/exit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(commands))
    joi = Mock()
    joi.state = SimpleNamespace(voice_enabled=False)
    joi.status.return_value = {
        'app_name': 'JOI',
        'brain': {'ok': True, 'selected_model': 'model'},
        'mic': 'OFF',
        'voice': 'DISABLED',
        'vision': 'OFF',
        'memory': 'SESSION',
        'cloud': 'OFF',
    }
    joi.set_runtime_state.return_value = 'Memory: OFF'

    TerminalInterface(joi).run()

    joi.set_runtime_state.assert_called_once_with('memory', 'off')
    assert 'Memory: OFF' in capsys.readouterr().out


def test_terminal_reports_refused_runtime_state_command(monkeypatch, capsys):
    commands = iter(['/mic on', '/exit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(commands))
    joi = Mock()
    joi.state = SimpleNamespace(voice_enabled=False)
    joi.status.return_value = {
        'app_name': 'JOI',
        'brain': {'ok': True, 'selected_model': 'model'},
        'mic': 'OFF',
        'voice': 'DISABLED',
        'vision': 'OFF',
        'memory': 'SESSION',
        'cloud': 'OFF',
    }
    joi.set_runtime_state.side_effect = ValueError('MIC is not configured')

    TerminalInterface(joi).run()

    assert '[STATE ERROR] MIC is not configured' in capsys.readouterr().out


def _inspected_turn(status='original', effective_content='Original evidence'):
    turn = EpisodicTurn(
        turn_id='turn-1',
        exchange_id='exchange-1',
        role='user',
        content='Original evidence',
        created_at_utc='2026-08-31T12:00:00+00:00',
        schema_version=1,
    )
    policies = ()
    if status != 'original':
        policies = (MemoryPolicyRecord(
            policy_id='policy-1',
            target_turn_id='turn-1',
            action='forget' if status == 'forgotten' else 'correct',
            replacement_content=effective_content,
            reason='user request',
            supersedes_policy_id=None,
            created_at_utc='2026-08-31T12:30:00+00:00',
            schema_version=1,
        ),)
    return InspectedMemoryTurn(turn, status, effective_content, policies)


def test_terminal_memory_status_and_recent_commands(monkeypatch, capsys):
    commands = iter(['/memory status', '/memory recent 2', '/exit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(commands))
    joi = Mock()
    joi.state = SimpleNamespace(voice_enabled=False)
    joi.status.return_value = {
        'app_name': 'JOI',
        'brain': {'ok': True, 'selected_model': 'model'},
        'mic': 'OFF',
        'voice': 'DISABLED',
        'vision': 'OFF',
        'memory': 'PERSISTENT',
        'cloud': 'OFF',
    }
    joi.memory_store_status.return_value = {
        'schema_version': 2,
        'turn_count': 2,
        'exchange_count': 1,
        'policy_count': 0,
        'corrected_turn_count': 0,
        'forgotten_turn_count': 0,
    }
    joi.memory_recent.return_value = [_inspected_turn()]

    TerminalInterface(joi).run()

    output = capsys.readouterr().out
    assert 'Memory store: schema=2 turns=2 exchanges=1 policies=0' in output
    assert 'turn-1 | USER | ORIGINAL | Original evidence' in output
    joi.memory_recent.assert_called_once_with(2)


def test_terminal_memory_why_shows_raw_and_policy_provenance(monkeypatch, capsys):
    commands = iter(['/memory why turn-1', '/exit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(commands))
    joi = Mock()
    joi.state = SimpleNamespace(voice_enabled=False)
    joi.status.return_value = {
        'app_name': 'JOI',
        'brain': {'ok': True, 'selected_model': 'model'},
        'mic': 'OFF',
        'voice': 'DISABLED',
        'vision': 'OFF',
        'memory': 'PERSISTENT',
        'cloud': 'OFF',
    }
    joi.memory_why.return_value = _inspected_turn('corrected', 'Corrected evidence')

    TerminalInterface(joi).run()

    output = capsys.readouterr().out
    assert 'Raw: Original evidence' in output
    assert 'Effective: Corrected evidence' in output
    assert 'policy-1 | CORRECT | supersedes=none | reason=user request' in output


def test_terminal_memory_correction_preserves_case(monkeypatch, capsys):
    commands = iter(['/memory correct turn-1 Correct Value With Case', '/exit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(commands))
    joi = Mock()
    joi.state = SimpleNamespace(voice_enabled=False)
    joi.status.return_value = {
        'app_name': 'JOI',
        'brain': {'ok': True, 'selected_model': 'model'},
        'mic': 'OFF',
        'voice': 'DISABLED',
        'vision': 'OFF',
        'memory': 'PERSISTENT',
        'cloud': 'OFF',
    }
    joi.memory_correct.return_value = Mock(policy_id='policy-1')

    TerminalInterface(joi).run()

    joi.memory_correct.assert_called_once_with('turn-1', 'Correct Value With Case')
    assert 'Correction recorded: policy-1' in capsys.readouterr().out


def test_terminal_memory_forget_and_errors(monkeypatch, capsys):
    commands = iter(['/memory forget turn-1 User Request', '/memory why missing', '/exit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(commands))
    joi = Mock()
    joi.state = SimpleNamespace(voice_enabled=False)
    joi.status.return_value = {
        'app_name': 'JOI',
        'brain': {'ok': True, 'selected_model': 'model'},
        'mic': 'OFF',
        'voice': 'DISABLED',
        'vision': 'OFF',
        'memory': 'PERSISTENT',
        'cloud': 'OFF',
    }
    joi.memory_forget.return_value = Mock(policy_id='policy-1')
    joi.memory_why.side_effect = ValueError('turn not found: missing')

    TerminalInterface(joi).run()

    joi.memory_forget.assert_called_once_with('turn-1', 'User Request')
    output = capsys.readouterr().out
    assert 'Forget policy recorded: policy-1' in output
    assert '[MEMORY ERROR] turn not found: missing' in output