import hashlib
import json
from pathlib import Path


class ArtifactIntegrityError(RuntimeError):
    pass


def verify_artifact_manifest(manifest_path: str | Path) -> int:
    manifest_path = Path(manifest_path)
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        if payload.get('algorithm') != 'sha256':
            raise ArtifactIntegrityError('unsupported manifest algorithm')
        artifacts = payload['artifacts']
        if not isinstance(artifacts, list):
            raise TypeError
    except ArtifactIntegrityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ArtifactIntegrityError('artifact manifest is malformed') from exc

    for item in artifacts:
        try:
            relative_path = Path(item['path'])
            expected_hash = item['sha256']
            expected_bytes = item.get('bytes')
        except (KeyError, TypeError) as exc:
            raise ArtifactIntegrityError('artifact manifest is malformed') from exc
        if relative_path.is_absolute() or '..' in relative_path.parts:
            raise ArtifactIntegrityError('artifact manifest path is unsafe')
        artifact_path = manifest_path.parent / relative_path
        if not artifact_path.is_file():
            raise ArtifactIntegrityError(f'artifact is missing: {relative_path.as_posix()}')
        content = artifact_path.read_bytes()
        if expected_bytes is not None and len(content) != expected_bytes:
            raise ArtifactIntegrityError(f'artifact size mismatch: {relative_path.as_posix()}')
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ArtifactIntegrityError(f'artifact hash mismatch: {relative_path.as_posix()}')
    return len(artifacts)