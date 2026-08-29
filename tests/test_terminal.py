from types import SimpleNamespace
from unittest.mock import Mock

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