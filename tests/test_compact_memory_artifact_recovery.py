import json
from pathlib import Path

import pytest

from memory.compact_memory import (
    CompactMemoryError,
    CompactMemoryStore,
    ModelCompactMemoryStore,
    parse_model_candidate,
)


def _candidate_payload(policy_revision=0):
    generated = '2026-09-01T12:00:00+00:00'
    return {
        'summary_version': 1,
        'generated_at_utc': generated,
        'summarizer': 'model-v2:test:test-model',
        'source_policy_revision': policy_revision,
        'claims': [],
        'provider': 'test',
        'model': 'test-model',
    }


@pytest.mark.parametrize('corrupt_bytes', [
    b'{"summary_version": 1',
    b'\x00\xff\x10bit-flip',
    json.dumps({'summary_version': 99, 'claims': []}).encode('utf-8'),
])
def test_model_store_quarantines_corrupt_artifact_and_restart_recovers(
    tmp_path,
    corrupt_bytes,
):
    path = tmp_path / 'candidate.json'
    path.write_bytes(corrupt_bytes)
    store = ModelCompactMemoryStore(path)

    with pytest.raises(CompactMemoryError, match='quarantined'):
        store.load()

    assert not path.exists()
    quarantine = [
        item for item in tmp_path.glob('candidate.json.corrupt-*')
        if not item.name.endswith('.receipt.json')
    ]
    receipts = list(tmp_path.glob('candidate.json.corrupt-*.receipt.json'))
    assert len(quarantine) == 1
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding='utf-8'))
    assert receipt['reason'] == 'model candidate is malformed'
    assert receipt['original_path'] == 'candidate.json'
    assert 'content' not in receipt
    assert ModelCompactMemoryStore(path).load() is None


def test_missing_model_artifact_is_valid_empty_state(tmp_path):
    assert ModelCompactMemoryStore(tmp_path / 'missing.json').load() is None


def test_interrupted_write_is_quarantined_without_replacing_valid_candidate(tmp_path):
    path = tmp_path / 'candidate.json'
    candidate = parse_model_candidate(json.dumps(_candidate_payload()))
    ModelCompactMemoryStore(path).save(candidate)
    temporary_path = path.with_suffix('.json.tmp')
    temporary_path.write_text('{interrupted', encoding='utf-8')

    loaded = ModelCompactMemoryStore(path).load()

    assert loaded == candidate
    assert not temporary_path.exists()
    quarantine = [
        item for item in tmp_path.glob('candidate.json.tmp.corrupt-*')
        if not item.name.endswith('.receipt.json')
    ]
    assert len(quarantine) == 1


def test_stale_candidate_is_quarantined_against_current_policy(tmp_path):
    path = tmp_path / 'candidate.json'
    path.write_text(json.dumps(_candidate_payload(policy_revision=2)), encoding='utf-8')

    with pytest.raises(CompactMemoryError, match='stale.*quarantined'):
        ModelCompactMemoryStore(path).load(expected_policy_revision=3)

    assert not path.exists()


def test_extractive_store_quarantines_corrupt_artifact(tmp_path):
    path = tmp_path / 'compact-memory.json'
    path.write_text('{broken', encoding='utf-8')

    with pytest.raises(CompactMemoryError, match='quarantined'):
        CompactMemoryStore(path).load()

    assert not path.exists()
    assert CompactMemoryStore(path).load() is None


def test_quarantine_names_do_not_overwrite_prior_evidence(tmp_path):
    path = tmp_path / 'candidate.json'
    for _ in range(2):
        path.write_text('{broken', encoding='utf-8')
        with pytest.raises(CompactMemoryError, match='quarantined'):
            ModelCompactMemoryStore(path).load()

    quarantined = [
        item for item in tmp_path.glob('candidate.json.corrupt-*')
        if not item.name.endswith('.receipt.json')
    ]
    assert len(quarantined) == 2
    assert len({item.name for item in quarantined}) == 2