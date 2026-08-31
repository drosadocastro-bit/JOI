import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from memory.compact_memory import (
    CompactClaim,
    CompactMemoryDraft,
    CompactMemoryError,
    CompactMemoryManager,
    CompactMemoryState,
    CompactMemoryStore,
    CompactMemoryWorker,
    CompactSource,
    ExtractiveCompactSummarizer,
    ModelCompactMemoryManager,
    ModelCompactMemoryStore,
    ModelCompactSummarizer,
    CompactMemoryEvaluator,
    CompactEvaluationStore,
    parse_model_candidate,
)
from memory.memory_store import EffectiveMemorySnapshot, EffectiveMemoryTurn, EpisodicTurn


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


def _effective_snapshot(policy_revision=0, content='I prefer concise replies.'):
    return EffectiveMemorySnapshot(
        policy_revision=policy_revision,
        turns=(EffectiveMemoryTurn(
            turn_id='user-1',
            exchange_id='exchange-1',
            role='user',
            content=content,
            source_policy_id=None,
            forgotten=False,
            completed_exchange=True,
            created_at_utc='2026-08-30T12:00:00+00:00',
        ),),
    )


def _candidate_payload(**claim_overrides):
    claim = {
        'claim_id': 'claim-1',
        'text': 'I prefer concise replies.',
        'source_turn_ids': ['user-1'],
        'source_policy_ids': [None],
        'confidence': 0.95,
        'status': 'explicit',
        'generated_at_utc': '2026-08-30T12:30:00+00:00',
        'summarizer': 'model-v1:test-model',
    }
    claim.update(claim_overrides)
    return {
        'summary_version': 1,
        'generated_at_utc': '2026-08-30T12:30:00+00:00',
        'summarizer': 'model-v1:test-model',
        'source_policy_revision': 0,
        'claims': [claim],
    }


def test_model_candidate_parser_enforces_structured_claim_schema():
    candidate = parse_model_candidate(json.dumps(_candidate_payload()))

    assert candidate.claims == (CompactClaim(
        claim_id='claim-1',
        text='I prefer concise replies.',
        source_turn_ids=('user-1',),
        source_policy_ids=(None,),
        confidence=0.95,
        status='explicit',
        generated_at_utc='2026-08-30T12:30:00+00:00',
        summarizer='model-v1:test-model',
    ),)


@pytest.mark.parametrize(
    'payload, message',
    [
        ({'summary_version': 1}, 'model candidate is malformed'),
        (_candidate_payload(status='inferred'), 'inferred claims are not accepted'),
        (_candidate_payload(source_turn_ids=[]), 'claim provenance is malformed'),
    ],
)
def test_model_candidate_parser_rejects_unsafe_shapes(payload, message):
    with pytest.raises(CompactMemoryError, match=message):
        parse_model_candidate(json.dumps(payload))


def test_model_candidate_rejects_stale_or_unsupported_claim_and_preserves_state(tmp_path):
    path = tmp_path / 'model-candidate.json'
    store = ModelCompactMemoryStore(path)
    valid = parse_model_candidate(json.dumps(_candidate_payload()))
    store.save(valid)
    manager = ModelCompactMemoryManager(store=store, summarizer=Mock())
    manager.summarizer.return_value = parse_model_candidate(json.dumps(
        _candidate_payload(text='The user likes fabricated facts.'),
    ))

    with pytest.raises(CompactMemoryError, match='unsupported claim'):
        manager.update(_effective_snapshot())

    assert store.load() == valid


def test_model_candidate_accepts_current_corrected_provenance(tmp_path):
    snapshot = EffectiveMemorySnapshot(
        policy_revision=1,
        turns=(EffectiveMemoryTurn(
            turn_id='user-1',
            exchange_id='exchange-1',
            role='user',
            content='Green is my favorite.',
            source_policy_id='policy-1',
            forgotten=False,
            completed_exchange=True,
            created_at_utc='2026-08-30T12:00:00+00:00',
        ),),
    )
    payload = _candidate_payload(
        text='Green is my favorite.',
        source_policy_ids=['policy-1'],
    )
    payload['source_policy_revision'] = 1
    candidate = parse_model_candidate(json.dumps(payload))
    manager = ModelCompactMemoryManager(
        store=ModelCompactMemoryStore(tmp_path / 'model-candidate.json'),
        summarizer=Mock(return_value=candidate),
    )

    assert manager.update(snapshot) == candidate


def test_model_candidate_rejects_forgotten_and_stale_policy_sources(tmp_path):
    forgotten_payload = _candidate_payload(source_policy_ids=['policy-1'])
    forgotten_payload['source_policy_revision'] = 1
    manager = ModelCompactMemoryManager(
        store=ModelCompactMemoryStore(tmp_path / 'model-candidate.json'),
        summarizer=Mock(return_value=parse_model_candidate(json.dumps(forgotten_payload))),
    )
    forgotten = EffectiveMemorySnapshot(
        policy_revision=1,
        turns=(EffectiveMemoryTurn(
            turn_id='user-1', exchange_id='exchange-1', role='user', content=None,
            source_policy_id='policy-1', forgotten=True,
            completed_exchange=True,
            created_at_utc='2026-08-30T12:00:00+00:00',
        ),),
    )

    with pytest.raises(CompactMemoryError, match='forgotten source'):
        manager.update(forgotten)

    stale = _effective_snapshot(policy_revision=1)
    with pytest.raises(CompactMemoryError, match='source policy is stale'):
        manager.update(stale)


def test_model_summarizer_requests_json_from_effective_evidence():
    brain = Mock()
    brain.chat.return_value = json.dumps(_candidate_payload())
    summarizer = ModelCompactSummarizer(brain, model='test-model')

    candidate = summarizer(_effective_snapshot())

    assert candidate.claims[0].text == 'I prefer concise replies.'
    messages = brain.chat.call_args.args[0]
    assert messages[0]['role'] == 'system'
    assert 'JSON only' in messages[0]['content']
    assert 'I prefer concise replies.' in messages[1]['content']
    assert 'source_policy_revision": 0' in messages[1]['content']


def test_model_summarizer_rejects_invalid_json():
    brain = Mock()
    brain.chat.return_value = 'not json'

    with pytest.raises(CompactMemoryError, match='model candidate is malformed'):
        ModelCompactSummarizer(brain, model='test-model')(_effective_snapshot())


def test_evaluator_records_paired_baseline_and_candidate_metrics(tmp_path):
    candidate = parse_model_candidate(json.dumps(_candidate_payload()))
    manager = ModelCompactMemoryManager(
        ModelCompactMemoryStore(tmp_path / 'candidate.json'),
        Mock(return_value=candidate),
    )
    evaluator = CompactMemoryEvaluator(
        manager=manager,
        report_store=CompactEvaluationStore(tmp_path / 'evaluation.json'),
        clock=lambda: datetime(2026, 8, 30, 12, 31, tzinfo=timezone.utc),
    )

    report = evaluator.update(_effective_snapshot())

    assert report.accepted is True
    assert report.baseline_claim_count == 1
    assert report.candidate_claim_count == 1
    assert report.shared_claim_count == 1
    assert report.baseline_summary_version == 1
    assert report.baseline_summarizer == 'extractive-v1'
    assert report.factual_coverage == 1.0
    assert report.provenance_coverage == 1.0
    assert report.unsupported_claim_rate == 0.0
    assert report.source_policy_revision == 0
    assert report.baseline_output == [{
        'text': 'I prefer concise replies.',
        'source_turn_ids': ['user-1'],
        'source_policy_ids': [None],
    }]
    assert report.candidate_output[0]['claim_id'] == 'claim-1'
    assert CompactEvaluationStore(tmp_path / 'evaluation.json').load() == [report]


def test_evaluator_reports_rejection_without_replacing_candidate(tmp_path):
    valid = parse_model_candidate(json.dumps(_candidate_payload()))
    candidate_store = ModelCompactMemoryStore(tmp_path / 'candidate.json')
    candidate_store.save(valid)
    manager = ModelCompactMemoryManager(
        candidate_store,
        Mock(return_value=parse_model_candidate(json.dumps(
            _candidate_payload(text='Unsupported addition.'),
        ))),
    )
    evaluator = CompactMemoryEvaluator(
        manager=manager,
        report_store=CompactEvaluationStore(tmp_path / 'evaluation.json'),
    )

    report = evaluator.update(_effective_snapshot())

    assert report.accepted is False
    assert report.rejection_reason == 'unsupported claim'
    assert report.unsupported_claim_rate == 1.0
    assert candidate_store.load() == valid


def test_manager_rejects_incomplete_exchange_and_concurrent_policy_change(tmp_path):
    candidate = parse_model_candidate(json.dumps(_candidate_payload()))
    incomplete = _effective_snapshot()
    incomplete = EffectiveMemorySnapshot(
        policy_revision=0,
        turns=(EffectiveMemoryTurn(
            **{**incomplete.turns[0].__dict__, 'completed_exchange': False}
        ),),
    )
    manager = ModelCompactMemoryManager(
        ModelCompactMemoryStore(tmp_path / 'candidate.json'),
        Mock(return_value=candidate),
    )

    with pytest.raises(CompactMemoryError, match='incomplete exchange'):
        manager.update(incomplete)

    manager = ModelCompactMemoryManager(
        ModelCompactMemoryStore(tmp_path / 'candidate.json'),
        Mock(return_value=candidate),
        policy_revision_reader=lambda: 1,
    )
    with pytest.raises(CompactMemoryError, match='changed during generation'):
        manager.update(_effective_snapshot())
