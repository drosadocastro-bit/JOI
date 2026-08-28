import pytest

from config.settings import Settings


def test_settings_rejects_invalid_request_timeout(monkeypatch):
    monkeypatch.setenv('REQUEST_TIMEOUT_SECONDS', 'not-a-number')

    with pytest.raises(ValueError, match='REQUEST_TIMEOUT_SECONDS must be a positive integer'):
        Settings.load()


def test_settings_rejects_non_positive_request_timeout(monkeypatch):
    monkeypatch.setenv('REQUEST_TIMEOUT_SECONDS', '0')

    with pytest.raises(ValueError, match='REQUEST_TIMEOUT_SECONDS must be a positive integer'):
        Settings.load()


def test_settings_loads_kokoro_voice_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv('VOICE_ENABLED', 'true')
    monkeypatch.setenv('KOKORO_PYTHON', str(tmp_path / 'python.exe'))
    monkeypatch.setenv('KOKORO_MODEL_PATH', str(tmp_path / 'model.onnx'))
    monkeypatch.setenv('KOKORO_VOICES_PATH', str(tmp_path / 'voices.bin'))
    monkeypatch.setenv('TTS_VOICE', 'af_heart')
    monkeypatch.setenv('TTS_LANGUAGE', 'es')
    monkeypatch.setenv('TTS_TIMEOUT_SECONDS', '45')

    settings = Settings.load()

    assert settings.voice_enabled is True
    assert settings.kokoro_python == str(tmp_path / 'python.exe')
    assert settings.kokoro_model_path == str(tmp_path / 'model.onnx')
    assert settings.kokoro_voices_path == str(tmp_path / 'voices.bin')
    assert settings.tts_voice == 'af_heart'
    assert settings.tts_language == 'es'
    assert settings.tts_timeout_seconds == 45


def test_settings_rejects_invalid_tts_timeout(monkeypatch):
    monkeypatch.setenv('TTS_TIMEOUT_SECONDS', '0')

    with pytest.raises(ValueError, match='TTS_TIMEOUT_SECONDS must be a positive integer'):
        Settings.load()