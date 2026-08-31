import sqlite3
from datetime import datetime, timezone
from itertools import count

import pytest

from memory.memory_store import EpisodicMemoryStore, MemoryStoreError


def _store(tmp_path, identifiers=None):
    identifiers = iter(identifiers or ['exchange-1', 'turn-user-1', 'turn-assistant-1'])
    return EpisodicMemoryStore(
        tmp_path / 'episodic.sqlite3',
        id_factory=lambda: next(identifiers),
        clock=lambda: datetime(2026, 8, 28, 12, 30, tzinfo=timezone.utc),
    )


def test_append_exchange_persists_atomic_provenance(tmp_path):
    store = _store(tmp_path)

    turns = store.append_exchange('Hello', 'Hi there')

    assert [turn.turn_id for turn in turns] == ['turn-user-1', 'turn-assistant-1']
    assert [turn.role for turn in turns] == ['user', 'assistant']
    assert [turn.content for turn in turns] == ['Hello', 'Hi there']
    assert {turn.exchange_id for turn in turns} == {'exchange-1'}
    assert {turn.created_at_utc for turn in turns} == {'2026-08-28T12:30:00+00:00'}
    assert {turn.schema_version for turn in turns} == {1}
    assert store.list_turns() == turns


def test_append_exchange_rolls_back_both_turns_on_collision(tmp_path):
    store = _store(tmp_path, ['exchange-1', 'duplicate-turn', 'duplicate-turn'])

    with pytest.raises(MemoryStoreError, match='could not append exchange'):
        store.append_exchange('Hello', 'Hi there')

    assert store.list_turns() == []


@pytest.mark.parametrize('user_text, assistant_text', [('', 'reply'), ('question', ' ')])
def test_append_exchange_rejects_empty_content(tmp_path, user_text, assistant_text):
    store = _store(tmp_path)

    with pytest.raises(ValueError, match='must not be empty'):
        store.append_exchange(user_text, assistant_text)

    assert store.list_turns() == []


def test_store_rejects_unsupported_schema_without_rewriting_it(tmp_path):
    path = tmp_path / 'future.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA user_version = 99')

    with pytest.raises(MemoryStoreError, match='unsupported memory schema version: 99'):
        EpisodicMemoryStore(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 99


def test_corrupted_store_raises_bounded_error(tmp_path):
    path = tmp_path / 'corrupted.sqlite3'
    path.write_bytes(b'not a sqlite database')

    with pytest.raises(MemoryStoreError, match='could not initialize memory store'):
        EpisodicMemoryStore(path)


def test_raw_turns_are_append_only_at_database_boundary(tmp_path):
    store = _store(tmp_path)
    store.append_exchange('Original question', 'Original reply')

    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match='episodic turns are append-only'):
            connection.execute(
                "UPDATE episodic_turns SET content = 'rewritten' WHERE role = 'user'"
            )
        with pytest.raises(sqlite3.IntegrityError, match='episodic turns are append-only'):
            connection.execute("DELETE FROM episodic_turns WHERE role = 'assistant'")

    assert [turn.content for turn in store.list_turns()] == [
        'Original question',
        'Original reply',
    ]


def test_store_reopens_after_200_exchange_soak_with_provenance(tmp_path):
    path = tmp_path / 'episodic.sqlite3'
    identifiers = count(1)
    store = EpisodicMemoryStore(path, id_factory=lambda: f'id-{next(identifiers)}')

    for exchange_number in range(200):
        store.append_exchange(
            f'Question {exchange_number}',
            f'Answer {exchange_number}',
        )

    turns = EpisodicMemoryStore(path).list_turns()

    assert len(turns) == 400
    assert len({turn.turn_id for turn in turns}) == 400
    assert len({turn.exchange_id for turn in turns}) == 200
    assert [turn.role for turn in turns[:4]] == ['user', 'assistant', 'user', 'assistant']
    assert turns[0].content == 'Question 0'
    assert turns[-1].content == 'Answer 199'


def test_correction_supersedes_prior_policy_without_rewriting_raw_turn(tmp_path):
    identifiers = [
        'exchange-1',
        'turn-user-1',
        'turn-assistant-1',
        'policy-1',
        'policy-2',
    ]
    store = _store(tmp_path, identifiers)
    store.append_exchange('My favorite color is blue.', 'Noted.')

    first = store.correct_turn('turn-user-1', 'My favorite color is green.')
    second = store.correct_turn('turn-user-1', 'My favorite color is red.')
    inspected = store.inspect_turn('turn-user-1')

    assert first.supersedes_policy_id is None
    assert second.supersedes_policy_id == first.policy_id
    assert inspected.turn.content == 'My favorite color is blue.'
    assert inspected.effective_content == 'My favorite color is red.'
    assert inspected.status == 'corrected'
    assert inspected.policies == (first, second)


def test_forget_logically_suppresses_turn_without_deleting_evidence(tmp_path):
    store = _store(
        tmp_path,
        ['exchange-1', 'turn-user-1', 'turn-assistant-1', 'policy-1'],
    )
    store.append_exchange('Private detail.', 'Understood.')

    policy = store.forget_turn('turn-user-1', reason='user request')
    inspected = store.inspect_turn('turn-user-1')

    assert policy.action == 'forget'
    assert inspected.status == 'forgotten'
    assert inspected.effective_content is None
    assert inspected.turn.content == 'Private detail.'
    assert len(store.list_turns()) == 2


def test_policy_records_are_append_only_at_database_boundary(tmp_path):
    store = _store(
        tmp_path,
        ['exchange-1', 'turn-user-1', 'turn-assistant-1', 'policy-1'],
    )
    store.append_exchange('Original.', 'Reply.')
    store.correct_turn('turn-user-1', 'Corrected.')

    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match='memory policies are append-only'):
            connection.execute("UPDATE memory_policies SET action = 'forget'")
        with pytest.raises(sqlite3.IntegrityError, match='memory policies are append-only'):
            connection.execute('DELETE FROM memory_policies')


def test_policy_rejects_unknown_turn_and_empty_correction(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(MemoryStoreError, match='turn not found'):
        store.forget_turn('missing')
    with pytest.raises(ValueError, match='replacement content must not be empty'):
        store.correct_turn('missing', ' ')


def test_recent_inspection_returns_latest_turns_with_policy_status(tmp_path):
    identifiers = iter(
        ['exchange-1', 'user-1', 'assistant-1', 'exchange-2', 'user-2', 'assistant-2', 'policy-1']
    )
    store = EpisodicMemoryStore(tmp_path / 'episodic.sqlite3', id_factory=lambda: next(identifiers))
    store.append_exchange('First question', 'First answer')
    store.append_exchange('Second question', 'Second answer')
    store.forget_turn('user-2')

    recent = store.inspect_recent(limit=2)

    assert [item.turn.turn_id for item in recent] == ['user-2', 'assistant-2']
    assert [item.status for item in recent] == ['forgotten', 'original']


def test_schema_v1_migrates_without_changing_raw_turns(tmp_path):
    path = tmp_path / 'v1.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.executescript(
            '''
            CREATE TABLE episodic_turns (
                turn_id TEXT PRIMARY KEY,
                exchange_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                UNIQUE (exchange_id, sequence)
            );
            INSERT INTO episodic_turns VALUES (
                'turn-1', 'exchange-1', 0, 'user', 'Original evidence',
                '2026-08-31T12:00:00+00:00', 1
            );
            PRAGMA user_version = 1;
            '''
        )

    store = EpisodicMemoryStore(path)

    assert store.inspect_turn('turn-1').turn.content == 'Original evidence'
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2


def test_memory_status_reports_evidence_and_policy_counts(tmp_path):
    store = _store(
        tmp_path,
        ['exchange-1', 'turn-user-1', 'turn-assistant-1', 'policy-1'],
    )
    store.append_exchange('Original.', 'Reply.')
    store.correct_turn('turn-user-1', 'Corrected.')

    assert store.status() == {
        'schema_version': 2,
        'turn_count': 2,
        'exchange_count': 1,
        'policy_count': 1,
        'corrected_turn_count': 1,
        'forgotten_turn_count': 0,
    }


def test_effective_snapshot_tracks_corrections_forgets_and_policy_revision(tmp_path):
    store = _store(
        tmp_path,
        [
            'exchange-1', 'user-1', 'assistant-1',
            'policy-1', 'policy-2',
        ],
    )
    store.append_exchange('Blue is my favorite.', 'Noted.')
    store.correct_turn('user-1', 'Green is my favorite.')
    store.forget_turn('assistant-1')

    snapshot = store.effective_snapshot()

    assert snapshot.policy_revision == 2
    assert snapshot.turns[0].turn_id == 'user-1'
    assert snapshot.turns[0].content == 'Green is my favorite.'
    assert snapshot.turns[0].source_policy_id == 'policy-1'
    assert snapshot.turns[1].forgotten is True
    assert snapshot.turns[1].content is None


def test_effective_snapshot_can_exclude_forgotten_sources(tmp_path):
    store = _store(
        tmp_path,
        ['exchange-1', 'user-1', 'assistant-1', 'policy-1'],
    )
    store.append_exchange('Keep this.', 'Forget this reply.')
    store.forget_turn('assistant-1')

    snapshot = store.effective_snapshot(include_forgotten=False)

    assert [turn.turn_id for turn in snapshot.turns] == ['user-1']
