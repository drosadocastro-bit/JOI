import hashlib
import json

import pytest

from memory.artifact_integrity import ArtifactIntegrityError, verify_artifact_manifest


def _write_manifest(tmp_path, artifact_name='artifact.json', content=b'{}'):
    artifact = tmp_path / artifact_name
    artifact.write_bytes(content)
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({
        'algorithm': 'sha256',
        'artifacts': [{
            'path': artifact_name,
            'sha256': hashlib.sha256(content).hexdigest(),
            'bytes': len(content),
        }],
    }), encoding='utf-8')
    return manifest, artifact


def test_manifest_verifies_frozen_artifact(tmp_path):
    manifest, _ = _write_manifest(tmp_path)

    assert verify_artifact_manifest(manifest) == 1


@pytest.mark.parametrize('mutation, message', [
    (lambda artifact: artifact.write_bytes(b'{"bit": 1}'), 'size mismatch'),
    (lambda artifact: artifact.unlink(), 'artifact is missing'),
])
def test_manifest_fails_closed_without_repair(tmp_path, mutation, message):
    manifest, artifact = _write_manifest(tmp_path)
    original_manifest = manifest.read_bytes()
    mutation(artifact)

    with pytest.raises(ArtifactIntegrityError, match=message):
        verify_artifact_manifest(manifest)

    assert manifest.read_bytes() == original_manifest


def test_manifest_detects_same_size_bit_flip(tmp_path):
    manifest, artifact = _write_manifest(tmp_path, content=b'abcd')
    artifact.write_bytes(b'abce')

    with pytest.raises(ArtifactIntegrityError, match='hash mismatch'):
        verify_artifact_manifest(manifest)


def test_manifest_rejects_parent_path(tmp_path):
    manifest, _ = _write_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    payload['artifacts'][0]['path'] = '../outside.json'
    manifest.write_text(json.dumps(payload), encoding='utf-8')

    with pytest.raises(ArtifactIntegrityError, match='path is unsafe'):
        verify_artifact_manifest(manifest)