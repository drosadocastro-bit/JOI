from datetime import datetime, timezone

import pytest

from memory.compact_memory import (
    CompactClaim,
    CompactEvaluationStore,
    CompactMemoryEvaluator,
    ModelCompactMemoryCandidate,
    ModelCompactMemoryManager,
    ModelCompactMemoryStore,
)
from memory.memory_store import EffectiveMemorySnapshot, EffectiveMemoryTurn


class ExactStructuredSummarizer:
    def __call__(self, snapshot):
        generated_at = '2026-08-31T12:00:00+00:00'
        claims = tuple(
            CompactClaim(
                claim_id=f'claim-{turn.turn_id}',
                text=turn.content,
                source_turn_ids=(turn.turn_id,),
                source_policy_ids=(turn.source_policy_id,),
                confidence=1.0,
                status='explicit',
                generated_at_utc=generated_at,
                summarizer='model-v1:deterministic-test',
            )
            for turn in snapshot.turns
            if not turn.forgotten
        )
        return ModelCompactMemoryCandidate(
            summary_version=1,
            generated_at_utc=generated_at,
            summarizer='model-v1:deterministic-test',
            source_policy_revision=snapshot.policy_revision,
            claims=claims,
        )


def _snapshot(update_count):
    turns = tuple(
        EffectiveMemoryTurn(
            turn_id=f'turn-{index}',
            exchange_id=f'exchange-{index // 2}',
            role='user' if index % 2 == 0 else 'assistant',
            content=f'Explicit fact {index}.',
            source_policy_id=None,
            forgotten=False,
            completed_exchange=True,
            created_at_utc='2026-08-31T12:00:00+00:00',
        )
        for index in range(update_count * 2)
    )
    return EffectiveMemorySnapshot(policy_revision=0, turns=turns)


@pytest.mark.parametrize('update_count', [25, 50, 100, 200])
def test_drift_checkpoints_preserve_facts_and_provenance(tmp_path, update_count):
    evaluator = CompactMemoryEvaluator(
        manager=ModelCompactMemoryManager(
            ModelCompactMemoryStore(tmp_path / f'candidate-{update_count}.json'),
            ExactStructuredSummarizer(),
        ),
        report_store=CompactEvaluationStore(tmp_path / f'report-{update_count}.json'),
        clock=lambda: datetime(2026, 8, 31, 12, 30, tzinfo=timezone.utc),
    )

    report = evaluator.update(_snapshot(update_count), checkpoint=update_count)

    assert report.checkpoint == update_count
    assert report.accepted is True
    assert report.factual_coverage == 1.0
    assert report.unsupported_claim_rate == 0.0
    assert report.provenance_coverage == 1.0
    assert report.stale_claim_rate == 0.0