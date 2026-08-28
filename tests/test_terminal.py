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