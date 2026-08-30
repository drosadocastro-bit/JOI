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
