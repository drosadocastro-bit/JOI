import ctypes
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


_PROVIDERS = {'openai', 'elevenlabs'}
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class CredentialAccessError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ('cbData', ctypes.c_ulong),
        ('pbData', ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob(data: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(data)
    return (
        _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))),
        buffer,
    )


def _dpapi(operation: str, data: bytes, description: str = '') -> bytes:
    if os.name != 'nt':
        raise CredentialAccessError('Windows DPAPI is unavailable')
    input_blob, input_buffer = _blob(data)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if operation == 'protect':
        success = crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            description,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
    else:
        success = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
    del input_buffer
    if not success:
        raise CredentialAccessError('Windows DPAPI operation failed')
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


class DpapiCredentialStore:
    source_type = 'windows_dpapi_user'

    def __init__(self, root: str | Path | None = None):
        local_app_data = os.getenv('LOCALAPPDATA')
        if root is None and not local_app_data:
            raise CredentialAccessError('LOCALAPPDATA is unavailable')
        self.root = Path(root) if root is not None else Path(local_app_data) / 'JOI' / 'credentials'

    @staticmethod
    def _validate_provider(provider: str) -> None:
        if provider not in _PROVIDERS:
            raise CredentialAccessError('unsupported credential provider')

    def _path(self, provider: str) -> Path:
        self._validate_provider(provider)
        return self.root / f'{provider}.dpapi'

    def set_credential(self, provider: str, credential: str) -> None:
        if not credential:
            raise CredentialAccessError('credential must not be empty')
        path = self._path(provider)
        protected = _dpapi('protect', credential.encode('utf-8'), f'JOI:{provider}')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix('.tmp')
        try:
            temporary_path.write_bytes(protected)
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def get_credential(self, provider: str) -> str:
        path = self._path(provider)
        try:
            protected = path.read_bytes()
            credential = _dpapi('unprotect', protected).decode('utf-8')
        except (OSError, UnicodeError, CredentialAccessError) as exc:
            raise CredentialAccessError(f'{provider} credential is unavailable') from exc
        if not credential:
            raise CredentialAccessError(f'{provider} credential is unavailable')
        return credential

    def delete_credential(self, provider: str) -> None:
        self._path(provider).unlink(missing_ok=True)


class CredentialProvider:
    def __init__(
        self,
        store: DpapiCredentialStore | None = None,
        audit_sink: Callable[[dict], None] | None = None,
    ):
        self._store = store or DpapiCredentialStore()
        self._audit_sink = audit_sink

    def __repr__(self) -> str:
        return 'CredentialProvider(source_type=windows_dpapi_user)'

    def get_openai_credential(self) -> str:
        return self._get('openai')

    def get_elevenlabs_credential(self) -> str:
        return self._get('elevenlabs')

    def _get(self, provider: str) -> str:
        try:
            credential = self._store.get_credential(provider)
        except Exception as exc:
            self._audit(provider, False)
            if isinstance(exc, CredentialAccessError):
                raise
            raise CredentialAccessError(f'{provider} credential is unavailable') from exc
        self._audit(provider, True)
        return credential

    def _audit(self, provider: str, success: bool) -> None:
        if self._audit_sink is None:
            return
        self._audit_sink({
            'provider': provider,
            'source_type': self._store.source_type,
            'success': success,
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        })


def write_audit_event(path: str | Path, event: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, sort_keys=True, separators=(',', ':')) + '\n')