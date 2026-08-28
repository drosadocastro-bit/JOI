import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import voice.voice_router as voice_router_module
from voice.voice_router import KokoroVoiceRouter


def _router(tmp_path):
    return KokoroVoiceRouter(
        python_executable='kokoro-python',
        model_path='model.onnx',
        voices_path='voices.bin',
        voice='af_heart',
        language='es',
        output_path=tmp_path / 'reply.wav',
        timeout_seconds=30,
    )


def test_speak_runs_isolated_worker_and_plays_result(monkeypatch, tmp_path):
    output_path = tmp_path / 'reply.wav'

    def run_worker(*args, **kwargs):
        output_path.write_bytes(b'RIFF')
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({'output': str(output_path)}),
            stderr='',
        )

    run = Mock(side_effect=run_worker)
    play_wav = Mock()
    monkeypatch.setattr(voice_router_module.subprocess, 'run', run)
    monkeypatch.setattr(voice_router_module, 'play_wav', play_wav)
    router = _router(tmp_path)

    router.speak('Hola, corazón.')

    command = run.call_args.args[0]
    assert command[0] == 'kokoro-python'
    assert command[1].endswith('kokoro_worker.py')
    assert '--model' in command and 'model.onnx' in command
    assert '--language' in command and 'es' in command
    assert run.call_args.kwargs['input'] == 'Hola, corazón.'
    assert run.call_args.kwargs['timeout'] == 30
    play_wav.assert_called_once_with(output_path, device_index=None)


def test_speak_reports_worker_failure_without_playback(monkeypatch, tmp_path):
    monkeypatch.setattr(
        voice_router_module.subprocess,
        'run',
        Mock(return_value=SimpleNamespace(returncode=1, stdout='', stderr='model failed')),
    )
    play_wav = Mock()
    monkeypatch.setattr(voice_router_module, 'play_wav', play_wav)

    with pytest.raises(RuntimeError, match='model failed'):
        _router(tmp_path).speak('Hello')

    play_wav.assert_not_called()


def test_speak_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError, match='text must not be empty'):
        _router(tmp_path).speak('  ')