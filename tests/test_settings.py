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
    monkeypatch.setenv('VOICE_MODE', 'local')
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


def test_settings_defaults_voice_mode_to_local(monkeypatch):
    monkeypatch.setenv('VOICE_MODE', 'local')

    assert Settings.load().voice_mode == 'local'


def test_settings_rejects_invalid_voice_mode(monkeypatch):
    monkeypatch.setenv('VOICE_MODE', 'automatic')

    with pytest.raises(ValueError, match='VOICE_MODE must be one of'):
        Settings.load()


def test_settings_rejects_online_voice_without_cloud_opt_in(monkeypatch):
    monkeypatch.setenv('VOICE_ENABLED', 'true')
    monkeypatch.setenv('VOICE_MODE', 'online')
    monkeypatch.setenv('CLOUD_ENABLED', 'false')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'local-secret')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'voice-id')

    with pytest.raises(ValueError, match='requires CLOUD_ENABLED=true'):
        Settings.load()


def test_settings_rejects_online_voice_without_credentials(monkeypatch):
    monkeypatch.setenv('VOICE_ENABLED', 'true')
    monkeypatch.setenv('VOICE_MODE', 'hybrid')
    monkeypatch.setenv('CLOUD_ENABLED', 'true')
    monkeypatch.setenv('ELEVENLABS_API_KEY', '')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', '')

    with pytest.raises(ValueError, match='requires ELEVENLABS_API_KEY'):
        Settings.load()


def test_settings_selects_spanish_elevenlabs_voice(monkeypatch):
    monkeypatch.setenv('VOICE_ENABLED', 'true')
    monkeypatch.setenv('VOICE_MODE', 'online')
    monkeypatch.setenv('CLOUD_ENABLED', 'true')
    monkeypatch.setenv('TTS_LANGUAGE', 'es')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'local-secret')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'english-voice')
    monkeypatch.setenv('ELEVENLABS_SPANISH_VOICE_ID', 'spanish-voice')

    settings = Settings.load()

    assert settings.elevenlabs_voice_id == 'spanish-voice'


def test_settings_requires_spanish_voice_for_spanish_online_mode(monkeypatch):
    monkeypatch.setenv('VOICE_ENABLED', 'true')
    monkeypatch.setenv('VOICE_MODE', 'online')
    monkeypatch.setenv('CLOUD_ENABLED', 'true')
    monkeypatch.setenv('TTS_LANGUAGE', 'es')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'local-secret')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'english-voice')
    monkeypatch.setenv('ELEVENLABS_SPANISH_VOICE_ID', '')

    with pytest.raises(ValueError, match='requires ELEVENLABS_SPANISH_VOICE_ID'):
        Settings.load()


@pytest.mark.parametrize(
    'base_url',
    [
        'http://api.elevenlabs.io/v1',
        'https://example.com/v1',
        'https://api.elevenlabs.io.example.com/v1',
    ],
)
def test_settings_rejects_untrusted_elevenlabs_base_url(monkeypatch, base_url):
    monkeypatch.setenv('VOICE_ENABLED', 'true')
    monkeypatch.setenv('VOICE_MODE', 'online')
    monkeypatch.setenv('CLOUD_ENABLED', 'true')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'local-secret')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'voice-id')
    monkeypatch.setenv('ELEVENLABS_BASE_URL', base_url)

    with pytest.raises(ValueError, match='official HTTPS ElevenLabs endpoint'):
        Settings.load()


def test_local_mode_ignores_untrusted_unused_cloud_endpoint(monkeypatch):
    monkeypatch.setenv('VOICE_MODE', 'local')
    monkeypatch.setenv('ELEVENLABS_BASE_URL', 'http://example.com/v1')

    assert Settings.load().voice_mode == 'local'


def test_settings_rejects_invalid_memory_mode(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'archive')

    with pytest.raises(ValueError, match='MEMORY_MODE must be one of: off, persistent, session'):
        Settings.load()


def test_settings_requires_feature_flag_for_persistent_memory(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'persistent')
    monkeypatch.setenv('ENABLE_PERSISTENT_MEMORY', 'false')

    with pytest.raises(ValueError, match='persistent memory requires ENABLE_PERSISTENT_MEMORY=true'):
        Settings.load()


def test_settings_enables_persistent_memory_explicitly(monkeypatch, tmp_path):
    path = tmp_path / 'episodic.sqlite3'
    monkeypatch.setenv('MEMORY_MODE', 'persistent')
    monkeypatch.setenv('ENABLE_PERSISTENT_MEMORY', 'true')
    monkeypatch.setenv('MEMORY_STORE_PATH', str(path))

    settings = Settings.load()

    assert settings.persistent_memory_enabled is True
    assert settings.memory_mode == 'persistent'
    assert settings.memory_store_path == str(path)


def test_settings_defaults_compact_memory_to_disabled(monkeypatch):
    monkeypatch.delenv('ENABLE_COMPACT_MEMORY', raising=False)

    assert Settings.load().compact_memory_enabled is False


def test_settings_requires_persistent_mode_for_compact_memory(monkeypatch):
    monkeypatch.setenv('ENABLE_PERSISTENT_MEMORY', 'true')
    monkeypatch.setenv('ENABLE_COMPACT_MEMORY', 'true')
    monkeypatch.setenv('MEMORY_MODE', 'session')

    with pytest.raises(ValueError, match='compact memory requires MEMORY_MODE=persistent'):
        Settings.load()


def test_settings_loads_compact_memory_configuration(monkeypatch, tmp_path):
    path = tmp_path / 'compact-memory.json'
    monkeypatch.setenv('ENABLE_PERSISTENT_MEMORY', 'true')
    monkeypatch.setenv('ENABLE_COMPACT_MEMORY', 'true')
    monkeypatch.setenv('MEMORY_MODE', 'persistent')
    monkeypatch.setenv('COMPACT_MEMORY_PATH', str(path))
    monkeypatch.setenv('COMPACT_MEMORY_MAX_CHARACTERS', '1500')

    settings = Settings.load()

    assert settings.compact_memory_enabled is True
    assert settings.compact_memory_path == str(path)
    assert settings.compact_memory_max_characters == 1500


def test_settings_rejects_too_small_compact_memory_limit(monkeypatch):
    monkeypatch.setenv('COMPACT_MEMORY_MAX_CHARACTERS', '99')

    with pytest.raises(ValueError, match='must be at least 100'):
        Settings.load()


def test_settings_defaults_model_compact_memory_to_disabled(monkeypatch):
    monkeypatch.delenv('ENABLE_MODEL_COMPACT_MEMORY', raising=False)

    settings = Settings.load()

    assert settings.model_compact_memory_enabled is False


def test_settings_requires_compact_memory_for_model_candidate(monkeypatch):
    monkeypatch.setenv('ENABLE_MODEL_COMPACT_MEMORY', 'true')

    with pytest.raises(
        ValueError,
        match='model compact memory requires ENABLE_COMPACT_MEMORY=true',
    ):
        Settings.load()


def test_settings_loads_model_compact_memory_paths(monkeypatch, tmp_path):
    candidate_path = tmp_path / 'candidate.json'
    report_path = tmp_path / 'evaluation.json'
    monkeypatch.setenv('ENABLE_PERSISTENT_MEMORY', 'true')
    monkeypatch.setenv('ENABLE_COMPACT_MEMORY', 'true')
    monkeypatch.setenv('ENABLE_MODEL_COMPACT_MEMORY', 'true')
    monkeypatch.setenv('MEMORY_MODE', 'persistent')
    monkeypatch.setenv('MODEL_COMPACT_MEMORY_PATH', str(candidate_path))
    monkeypatch.setenv('COMPACT_MEMORY_EVALUATION_PATH', str(report_path))

    settings = Settings.load()

    assert settings.model_compact_memory_enabled is True
    assert settings.model_compact_memory_path == str(candidate_path)
    assert settings.compact_memory_evaluation_path == str(report_path)