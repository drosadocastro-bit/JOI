from datetime import datetime, timezone

from memory.compact_memory import (
    CompactClaim,
    CompactEvaluationStore,
    CompactMemoryEvaluator,
    ModelCompactMemoryCandidate,
    ModelCompactMemoryManager,
    ModelCompactMemoryStore,
)
from memory.memory_store import EpisodicMemoryStore


class EffectiveCopySummarizer:
    def __call__(self, snapshot):
        generated_at = '2026-08-31T12:30:00+00:00'
        return ModelCompactMemoryCandidate(
            summary_version=1,
            generated_at_utc=generated_at,
            summarizer='model-v1:effective-copy-test',
            source_policy_revision=snapshot.policy_revision,
            claims=tuple(
                CompactClaim(
                    claim_id=f'claim-{turn.turn_id}-{snapshot.policy_revision}',
                    text=turn.content,
                    source_turn_ids=(turn.turn_id,),
                    source_policy_ids=(turn.source_policy_id,),
                    confidence=1.0,
                    status='explicit',
                    generated_at_utc=generated_at,
                    summarizer='model-v1:effective-copy-test',
                )
                for turn in snapshot.turns
                if not turn.forgotten
            ),
        )


def test_correction_and_forgetting_regenerate_from_effective_evidence(tmp_path):
    identifiers = iter([
        'exchange-1', 'user-1', 'assistant-1', 'policy-1', 'policy-2',
    ])
    store = EpisodicMemoryStore(
        tmp_path / 'episodic.sqlite3',
        id_factory=lambda: next(identifiers),
        clock=lambda: datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
    )
    store.append_exchange('My color is blue.', 'Noted.')
    candidate_store = ModelCompactMemoryStore(tmp_path / 'candidate.json')
    evaluator = CompactMemoryEvaluator(
        manager=ModelCompactMemoryManager(
            candidate_store,
            EffectiveCopySummarizer(),
            policy_revision_reader=lambda: store.effective_snapshot().policy_revision,
        ),
        report_store=CompactEvaluationStore(tmp_path / 'evaluation.json'),
    )

    evaluator.update(store.effective_snapshot())
    store.correct_turn('user-1', 'My color is green.')
    evaluator.update(store.effective_snapshot())
    corrected = candidate_store.load()
    store.forget_turn('user-1')
    evaluator.update(store.effective_snapshot())
    forgotten = candidate_store.load()

    assert corrected is not None
    assert 'My color is green.' in {claim.text for claim in corrected.claims}
    assert 'My color is blue.' not in {claim.text for claim in corrected.claims}
    assert forgotten is not None
    assert 'user-1' not in {
        turn_id for claim in forgotten.claims for turn_id in claim.source_turn_ids
    }
    reports = CompactEvaluationStore(tmp_path / 'evaluation.json').load()
    assert [report.source_policy_revision for report in reports] == [0, 1, 2]