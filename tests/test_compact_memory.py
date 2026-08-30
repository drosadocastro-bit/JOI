import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from memory.compact_memory import (
    CompactMemoryDraft,
    CompactMemoryError,
    CompactMemoryManager,
    CompactMemoryState,
    CompactMemoryStore,
    CompactMemoryWorker,
    CompactSource,
    ExtractiveCompactSummarizer,
)
from memory.memory_store import EpisodicTurn


def _turn(turn_id, role, content):
    return EpisodicTurn(
        turn_id=turn_id,
        exchange_id='exchange-1',
        role=role,
        content=content,
        created_at_utc='2026-08-30T12:00:00+00:00',
        schema_version=1,
    )


def _manager(tmp_path, max_characters=500):
    return CompactMemoryManager(
        store=CompactMemoryStore(tmp_path / 'compact-memory.json'),
        summarizer=ExtractiveCompactSummarizer(max_characters=max_characters),
        clock=lambda: datetime(2026, 8, 30, 12, 30, tzinfo=timezone.utc),
    )


def test_compact_memory_updates_with_reconstructable_provenance(tmp_path):
    manager = _manager(tmp_path)
    turns = (
        _turn('user-1', 'user', 'My preferred editor theme is light.'),
        _turn('assistant-1', 'assistant', 'I will keep that preference in context.'),
    )

    state = manager.update(turns)
    reloaded = CompactMemoryStore(tmp_path / 'compact-memory.json').load()

    assert reloaded == state
    assert state.source_turn_ids == ('user-1', 'assistant-1')
    assert state.updated_at_utc == '2026-08-30T12:30:00+00:00'
    assert state.summarizer_version == 'extractive-v1'
    assert state.schema_version == 1
    assert '[user-1] USER: My preferred editor theme is light.' in state.summary
    assert state.summary == '\n'.join(source.render() for source in state.sources)


def test_compact_memory_is_bounded_and_keeps_complete_latest_exchange(tmp_path):
    manager = _manager(tmp_path, max_characters=120)
    manager.update((
        _turn('old-user', 'user', 'An older preference that should age out.'),
        _turn('old-assistant', 'assistant', 'An older acknowledgement.'),
    ))

    state = manager.update((
        _turn('new-user', 'user', 'The current project is JOI.'),
        _turn('new-assistant', 'assistant', 'The current project remains JOI.'),
    ))

    assert state.source_turn_ids == ('new-user', 'new-assistant')
    assert len(state.summary) <= 120


def test_failed_update_leaves_previous_valid_summary_intact(tmp_path):
    manager = _manager(tmp_path)
    original = manager.update((
        _turn('user-1', 'user', 'Original evidence.'),
        _turn('assistant-1', 'assistant', 'Original reply.'),
    ))
    manager.summarizer = lambda previous, turns: {'summary': 'untrusted shape'}

    with pytest.raises(CompactMemoryError, match='summarizer returned an invalid draft'):
        manager.update((
            _turn('user-2', 'user', 'New evidence.'),
            _turn('assistant-2', 'assistant', 'New reply.'),
        ))

    assert manager.state == original
    assert CompactMemoryStore(tmp_path / 'compact-memory.json').load() == original


def test_store_rejects_malformed_summary_without_rewriting_it(tmp_path):
    path = tmp_path / 'compact-memory.json'
    path.write_text(json.dumps({'schema_version': 1, 'summary': 42}), encoding='utf-8')

    with pytest.raises(CompactMemoryError, match='compact memory is malformed'):
        CompactMemoryStore(path).load()


def test_extractive_summary_contains_only_source_excerpts(tmp_path):
    manager = _manager(tmp_path)
    state = manager.update((
        _turn('user-1', 'user', 'I like synthwave.'),
        _turn('assistant-1', 'assistant', 'You said you like synthwave.'),
    ))

    assert 'always listens while driving' not in state.summary
    assert {source.content for source in state.sources} == {
        'I like synthwave.',
        'You said you like synthwave.',
    }


def test_manager_rejects_summary_that_alters_source_evidence(tmp_path):
    class ContradictingSummarizer:
        version = 'unsafe-test-v1'

        def __call__(self, previous, turns):
            return CompactMemoryDraft(sources=(
                CompactSource('user-1', 'user', 'I dislike synthwave.'),
                CompactSource('assistant-1', 'assistant', 'Noted.'),
            ))

    manager = CompactMemoryManager(
        store=CompactMemoryStore(tmp_path / 'compact-memory.json'),
        summarizer=ContradictingSummarizer(),
    )

    with pytest.raises(CompactMemoryError, match='contradicted source excerpts'):
        manager.update((
            _turn('user-1', 'user', 'I like synthwave.'),
            _turn('assistant-1', 'assistant', 'Noted.'),
        ))

    assert manager.state is None
    assert not (tmp_path / 'compact-memory.json').exists()


def test_worker_logs_failed_update_and_processes_next_job():
    valid_state = CompactMemoryState(
        summary='[user-2] USER: Valid',
        sources=(CompactSource('user-2', 'user', 'Valid'),),
        source_turn_ids=('user-2',),
        updated_at_utc='2026-08-30T12:30:00+00:00',
        summarizer_version='extractive-v1',
    )
    manager = Mock()
    manager.update.side_effect = [RuntimeError('bad update'), valid_state]
    logger = Mock()
    worker = CompactMemoryWorker(manager, logger)

    worker.submit((_turn('user-1', 'user', 'First'),))
    worker.submit((_turn('user-2', 'user', 'Second'),))
    worker.close()

    assert manager.update.call_count == 2
    assert worker.thread.is_alive() is False
    logger.exception.assert_called_once_with('Compact memory shadow update failed')
    logger.info.assert_called_once_with(
        'Compact memory shadow updated: sources=%d version=%s',
        1,
        'extractive-v1',
    )


def test_closed_worker_refuses_new_updates():
    worker = CompactMemoryWorker(Mock(), Mock())
    worker.close()

    with pytest.raises(CompactMemoryError, match='worker is closed'):
        worker.submit((_turn('user-1', 'user', 'Too late'),))
