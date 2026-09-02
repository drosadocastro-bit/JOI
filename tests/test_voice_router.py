import io
import json
import socket
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import voice.voice_router as voice_router_module
from voice.voice_router import (
    ElevenLabsVoiceProvider,
    KokoroVoiceRouter,
    NoRedirectHandler,
    VoiceRouter,
)


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


def test_voice_router_uses_only_local_provider_in_local_mode():
    local = Mock()
    online = Mock()
    router = VoiceRouter(mode='local', local_provider=local, online_provider=online)

    result = router.speak('Hello')

    local.speak.assert_called_once_with('Hello')
    online.speak.assert_not_called()
    assert result == local.speak.return_value
    assert router.active_provider == 'local'


def test_voice_router_online_mode_does_not_silently_fallback():
    local = Mock()
    online = Mock()
    online.speak.side_effect = RuntimeError('provider unavailable')
    router = VoiceRouter(mode='online', local_provider=local, online_provider=online)

    with pytest.raises(RuntimeError, match='provider unavailable'):
        router.speak('Hello')

    local.speak.assert_not_called()


def test_voice_router_hybrid_mode_falls_back_to_local():
    local = Mock()
    online = Mock()
    online.speak.side_effect = RuntimeError('provider unavailable')
    logger = Mock()
    router = VoiceRouter(
        mode='hybrid',
        local_provider=local,
        online_provider=online,
        logger=logger,
    )

    result = router.speak('Hello')

    online.speak.assert_called_once_with('Hello')
    local.speak.assert_called_once_with('Hello')
    logger.warning.assert_called_once()
    assert result == local.speak.return_value
    assert router.active_provider == 'local'


def _elevenlabs_provider(tmp_path, opener):
    credential_provider = Mock()
    credential_provider.get_elevenlabs_credential.return_value = 'test-credential'
    return ElevenLabsVoiceProvider(
        credential_provider=credential_provider,
        voice_id='voice-id',
        model_id='eleven_multilingual_v2',
        base_url='https://api.elevenlabs.io/v1',
        output_path=tmp_path / 'elevenlabs.wav',
        timeout_seconds=15,
        cloud_authorized=lambda: True,
        opener=opener,
    )


def _wav_bytes():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\x00\x00' * 240)
    return output.getvalue()


def test_elevenlabs_writes_validated_wav_and_plays_it(monkeypatch, tmp_path):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.headers = {'Content-Type': 'audio/wav'}
    response.read.return_value = _wav_bytes()
    opener = Mock(return_value=response)
    play_wav = Mock()
    monkeypatch.setattr(voice_router_module, 'play_wav', play_wav)
    provider = _elevenlabs_provider(tmp_path, opener)

    result = provider.speak('Hello')

    request = opener.call_args.args[0]
    assert request.full_url.endswith('/text-to-speech/voice-id?output_format=wav_24000')
    assert json.loads(request.data) == {
        'text': 'Hello',
        'model_id': 'eleven_multilingual_v2',
    }
    assert opener.call_args.kwargs['timeout'] == 15
    assert result.read_bytes() == response.read.return_value
    play_wav.assert_called_once_with(result, device_index=None)


def test_elevenlabs_timeout_does_not_play_audio(monkeypatch, tmp_path):
    play_wav = Mock()
    monkeypatch.setattr(voice_router_module, 'play_wav', play_wav)
    provider = _elevenlabs_provider(
        tmp_path,
        Mock(side_effect=socket.timeout('timed out')),
    )

    with pytest.raises(RuntimeError, match='ElevenLabs request failed'):
        provider.speak('Hello')

    play_wav.assert_not_called()
    assert not (tmp_path / 'elevenlabs.wav').exists()


def test_elevenlabs_rejects_malformed_audio(monkeypatch, tmp_path):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.headers = {'Content-Type': 'application/json'}
    response.read.return_value = b'{"detail":"not audio"}'
    play_wav = Mock()
    monkeypatch.setattr(voice_router_module, 'play_wav', play_wav)
    provider = _elevenlabs_provider(tmp_path, Mock(return_value=response))

    with pytest.raises(RuntimeError, match='invalid audio response'):
        provider.speak('Hello')

    play_wav.assert_not_called()
    assert not (tmp_path / 'elevenlabs.wav').exists()


def test_elevenlabs_redirects_are_refused():
    handler = NoRedirectHandler()

    assert handler.redirect_request(None, None, 302, 'Found', {}, 'https://example.com') is None


def test_elevenlabs_cloud_off_never_requests_credential(tmp_path):
    credential_provider = Mock()
    opener = Mock()
    provider = ElevenLabsVoiceProvider(
        credential_provider=credential_provider,
        voice_id='voice-id',
        model_id='eleven_multilingual_v2',
        base_url='https://api.elevenlabs.io/v1',
        output_path=tmp_path / 'elevenlabs.wav',
        timeout_seconds=15,
        cloud_authorized=lambda: False,
        opener=opener,
    )

    with pytest.raises(RuntimeError, match='CLOUD is OFF'):
        provider.speak('Hello')

    credential_provider.get_elevenlabs_credential.assert_not_called()
    opener.assert_not_called()


def test_elevenlabs_error_has_no_credential_or_chained_cause(tmp_path):
    credential = 'test-sensitive-credential'
    credential_provider = Mock()
    credential_provider.get_elevenlabs_credential.return_value = credential
    provider = ElevenLabsVoiceProvider(
        credential_provider=credential_provider,
        voice_id='voice-id',
        model_id='eleven_multilingual_v2',
        base_url='https://api.elevenlabs.io/v1',
        output_path=tmp_path / 'elevenlabs.wav',
        timeout_seconds=15,
        cloud_authorized=lambda: True,
        opener=Mock(side_effect=RuntimeError(f'header contained {credential}')),
    )

    with pytest.raises(RuntimeError) as error:
        provider.speak('Hello')

    assert credential not in str(error.value)
    assert error.value.__suppress_context__ is True


def test_elevenlabs_health_returns_no_account_or_credential_data(tmp_path):
    credential_provider = Mock()
    credential_provider.get_elevenlabs_credential.return_value = 'test-credential'
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b'{"subscription":{"tier":"private"}}'
    opener = Mock(return_value=response)
    provider = ElevenLabsVoiceProvider(
        credential_provider=credential_provider,
        voice_id='voice-id',
        model_id='eleven_multilingual_v2',
        base_url='https://api.elevenlabs.io/v1',
        output_path=tmp_path / 'elevenlabs.wav',
        timeout_seconds=15,
        cloud_authorized=lambda: True,
        opener=opener,
    )

    assert provider.health() == {'ok': True, 'provider': 'elevenlabs'}
    request = opener.call_args.args[0]
    assert request.full_url == 'https://api.elevenlabs.io/v1/user'