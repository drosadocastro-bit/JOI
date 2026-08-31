from dataclasses import dataclass, field
from pathlib import Path
import os
import urllib.parse


ELEVENLABS_HOSTS = {
    'api.elevenlabs.io',
    'api.us.elevenlabs.io',
    'api.eu.residency.elevenlabs.io',
    'api.in.residency.elevenlabs.io',
    'api.sg.residency.elevenlabs.io',
}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f'{name} must be a positive integer') from exc
    if value <= 0:
        raise ValueError(f'{name} must be a positive integer')
    return value


def _choice_env(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name, default).lower()
    if value not in choices:
        options = ', '.join(sorted(choices))
        raise ValueError(f'{name} must be one of: {options}')
    return value


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).lower()
    if value not in {'true', 'false'}:
        raise ValueError(f'{name} must be true or false')
    return value == 'true'


def _elevenlabs_base_url_env(required: bool) -> str:
    value = os.getenv('ELEVENLABS_BASE_URL', 'https://api.elevenlabs.io/v1').rstrip('/')
    if not required:
        return value
    parsed = urllib.parse.urlsplit(value)
    trusted = (
        parsed.scheme == 'https'
        and parsed.hostname in ELEVENLABS_HOSTS
        and parsed.port in {None, 443}
        and parsed.path == '/v1'
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )
    if not trusted:
        raise ValueError('ELEVENLABS_BASE_URL must be an official HTTPS ElevenLabs endpoint')
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str
    lmstudio_base_url: str
    local_model: str
    request_timeout_seconds: int
    log_level: str
    log_file: str
    voice_enabled: bool
    voice_mode: str
    kokoro_python: str
    kokoro_model_path: str
    kokoro_voices_path: str
    tts_voice: str
    tts_language: str
    tts_output_path: str
    tts_timeout_seconds: int
    elevenlabs_api_key: str = field(repr=False)
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    elevenlabs_base_url: str
    elevenlabs_timeout_seconds: int
    vision_enabled: bool
    cloud_enabled: bool
    memory_mode: str
    persistent_memory_enabled: bool
    memory_store_path: str
    compact_memory_enabled: bool
    compact_memory_path: str
    compact_memory_max_characters: int
    model_compact_memory_enabled: bool
    model_compact_memory_path: str
    compact_memory_evaluation_path: str

    @classmethod
    def load(cls):
        root = Path(__file__).resolve().parents[1]
        _load_dotenv(root / '.env')
        runtime_root = root.parents[1]
        voice_enabled = os.getenv('VOICE_ENABLED', 'false').lower() == 'true'
        voice_mode = _choice_env('VOICE_MODE', 'local', {'local', 'online', 'hybrid'})
        online_voice_enabled = voice_enabled and voice_mode in {'online', 'hybrid'}
        cloud_enabled = os.getenv('CLOUD_ENABLED', 'false').lower() == 'true'
        memory_mode = _choice_env('MEMORY_MODE', 'session', {'off', 'persistent', 'session'})
        persistent_memory_enabled = _bool_env('ENABLE_PERSISTENT_MEMORY')
        if memory_mode == 'persistent' and not persistent_memory_enabled:
            raise ValueError('persistent memory requires ENABLE_PERSISTENT_MEMORY=true')
        compact_memory_enabled = _bool_env('ENABLE_COMPACT_MEMORY')
        if compact_memory_enabled and memory_mode != 'persistent':
            raise ValueError('compact memory requires MEMORY_MODE=persistent')
        model_compact_memory_enabled = _bool_env('ENABLE_MODEL_COMPACT_MEMORY')
        if model_compact_memory_enabled and not compact_memory_enabled:
            raise ValueError(
                'model compact memory requires ENABLE_COMPACT_MEMORY=true'
            )
        compact_memory_max_characters = _positive_int_env(
            'COMPACT_MEMORY_MAX_CHARACTERS',
            2000,
        )
        if compact_memory_max_characters < 100:
            raise ValueError('COMPACT_MEMORY_MAX_CHARACTERS must be at least 100')
        tts_language = os.getenv('TTS_LANGUAGE', 'en-us').lower()
        elevenlabs_api_key = os.getenv('ELEVENLABS_API_KEY', '')
        elevenlabs_default_voice_id = os.getenv('ELEVENLABS_VOICE_ID', '')
        elevenlabs_spanish_voice_id = os.getenv('ELEVENLABS_SPANISH_VOICE_ID', '')
        use_spanish_voice = tts_language == 'es' or tts_language.startswith('es-')
        elevenlabs_voice_id = (
            elevenlabs_spanish_voice_id if use_spanish_voice else elevenlabs_default_voice_id
        )
        if online_voice_enabled:
            if not cloud_enabled:
                raise ValueError(f'{voice_mode} voice mode requires CLOUD_ENABLED=true')
            if not elevenlabs_api_key:
                raise ValueError(f'{voice_mode} voice mode requires ELEVENLABS_API_KEY')
            if not elevenlabs_voice_id:
                variable = (
                    'ELEVENLABS_SPANISH_VOICE_ID' if use_spanish_voice
                    else 'ELEVENLABS_VOICE_ID'
                )
                raise ValueError(f'{voice_mode} voice mode requires {variable}')

        return cls(
            app_name=os.getenv('JOI_APP_NAME', 'JOI 2.0'),
            lmstudio_base_url=os.getenv('LMSTUDIO_BASE_URL', 'http://127.0.0.1:1234/v1').rstrip('/'),
            local_model=os.getenv('LOCAL_MODEL', 'nvidia/nemotron-3-nano'),
            request_timeout_seconds=_positive_int_env('REQUEST_TIMEOUT_SECONDS', 300),
            log_level=os.getenv('LOG_LEVEL', 'INFO').upper(),
            log_file=os.getenv('LOG_FILE', str(root / 'data' / 'logs' / 'joi.log')),
            voice_enabled=voice_enabled,
            voice_mode=voice_mode,
            kokoro_python=os.getenv(
                'KOKORO_PYTHON',
                str(runtime_root / '.venv-kokoro' / 'Scripts' / 'python.exe'),
            ),
            kokoro_model_path=os.getenv(
                'KOKORO_MODEL_PATH',
                str(runtime_root / 'models' / 'kokoro' / 'kokoro-v1.0.onnx'),
            ),
            kokoro_voices_path=os.getenv(
                'KOKORO_VOICES_PATH',
                str(runtime_root / 'models' / 'kokoro' / 'voices-v1.0.bin'),
            ),
            tts_voice=os.getenv('TTS_VOICE', 'af_heart'),
            tts_language=tts_language,
            tts_output_path=os.getenv(
                'TTS_OUTPUT_PATH',
                str(root / 'data' / 'tts' / 'reply.wav'),
            ),
            tts_timeout_seconds=_positive_int_env('TTS_TIMEOUT_SECONDS', 120),
            elevenlabs_api_key=elevenlabs_api_key,
            elevenlabs_voice_id=elevenlabs_voice_id,
            elevenlabs_model_id=os.getenv('ELEVENLABS_MODEL_ID', 'eleven_multilingual_v2'),
            elevenlabs_base_url=_elevenlabs_base_url_env(online_voice_enabled),
            elevenlabs_timeout_seconds=_positive_int_env('ELEVENLABS_TIMEOUT_SECONDS', 30),
            vision_enabled=os.getenv('VISION_ENABLED', 'false').lower() == 'true',
            cloud_enabled=cloud_enabled,
            memory_mode=memory_mode,
            persistent_memory_enabled=persistent_memory_enabled,
            memory_store_path=os.getenv(
                'MEMORY_STORE_PATH',
                str(root / 'data' / 'memory' / 'episodic.sqlite3'),
            ),
            compact_memory_enabled=compact_memory_enabled,
            compact_memory_path=os.getenv(
                'COMPACT_MEMORY_PATH',
                str(root / 'data' / 'memory' / 'compact-memory.json'),
            ),
            compact_memory_max_characters=compact_memory_max_characters,
            model_compact_memory_enabled=model_compact_memory_enabled,
            model_compact_memory_path=os.getenv(
                'MODEL_COMPACT_MEMORY_PATH',
                str(root / 'data' / 'memory' / 'compact-memory-model-candidate.json'),
            ),
            compact_memory_evaluation_path=os.getenv(
                'COMPACT_MEMORY_EVALUATION_PATH',
                str(root / 'data' / 'memory' / 'compact-memory-evaluation.json'),
            ),
        )
