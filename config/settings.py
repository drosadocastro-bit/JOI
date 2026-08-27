from dataclasses import dataclass
from pathlib import Path
import os


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


@dataclass(frozen=True)
class Settings:
    app_name: str
    lmstudio_base_url: str
    local_model: str
    request_timeout_seconds: int
    log_level: str
    log_file: str
    voice_enabled: bool
    vision_enabled: bool
    cloud_enabled: bool
    memory_mode: str

    @classmethod
    def load(cls):
        root = Path(__file__).resolve().parents[1]
        _load_dotenv(root / '.env')
        return cls(
            app_name=os.getenv('JOI_APP_NAME', 'JOI 2.0'),
            lmstudio_base_url=os.getenv('LMSTUDIO_BASE_URL', 'http://127.0.0.1:1234/v1').rstrip('/'),
            local_model=os.getenv('LOCAL_MODEL', 'nvidia/nemotron-3-nano'),
            request_timeout_seconds=_positive_int_env('REQUEST_TIMEOUT_SECONDS', 300),
            log_level=os.getenv('LOG_LEVEL', 'INFO').upper(),
            log_file=os.getenv('LOG_FILE', str(root / 'data' / 'logs' / 'joi.log')),
            voice_enabled=os.getenv('VOICE_ENABLED', 'false').lower() == 'true',
            vision_enabled=os.getenv('VISION_ENABLED', 'false').lower() == 'true',
            cloud_enabled=os.getenv('CLOUD_ENABLED', 'false').lower() == 'true',
            memory_mode=os.getenv('MEMORY_MODE', 'session').lower(),
        )
