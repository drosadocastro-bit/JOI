import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from memory.memory_store import EffectiveMemorySnapshot, EffectiveMemoryTurn


SEMANTIC_LABELS = (
    'trivial_or_redundant',
    'preference',
    'correction_sensitive',
    'relationship_identity_relevant',
    'task_state',
    'safety_critical',
)
CATEGORY_WEIGHTS = {
    'trivial_or_redundant': 0,
    'preference': 1,
    'task_state': 2,
    'relationship_identity_relevant': 3,
    'correction_sensitive': 4,
    'safety_critical': 5,
}
PROTECTED_CATEGORIES = {
    'safety_critical',
    'correction_sensitive',
    'relationship_identity_relevant',
}
OMISSION_ADJUDICATIONS = {
    'acceptable_compression',
    'redundant_information',
    'harmful_omission',
    'reviewer_disagreement',
}
PROMOTION_CRITERIA = {
    'minimum_weighted_retention_score': 0.90,
    'minimum_critical_retention_rate': 1.0,
    'maximum_forbidden_loss_count': 0,
    'maximum_provenance_failure_count': 0,
    'maximum_harmful_omission_count': 0,
    'human_review_required': True,
    'systematic_critical_omission_rule': (
        'Any omitted safety-critical, correction-sensitive, or '
        'relationship/identity-relevant fact is a forbidden loss and fails.'
    ),
}


@dataclass(frozen=True)
class RetentionFact:
    turn_id: str
    role: str
    content: str
    semantic_label: str
    source_policy_id: str | None = None


class RetentionQualityCorpus:
    version = 'retention-quality-balanced-v1'
    _facts = (
        RetentionFact('trivial-1', 'assistant', 'Acknowledged your preference.', 'trivial_or_redundant'),
        RetentionFact('trivial-2', 'assistant', 'Understood.', 'trivial_or_redundant'),
        RetentionFact('trivial-3', 'assistant', 'I will keep that in mind.', 'trivial_or_redundant'),
        RetentionFact('trivial-4', 'assistant', 'Noted for this conversation.', 'trivial_or_redundant'),
        RetentionFact('preference-1', 'user', 'I prefer concise answers.', 'preference'),
        RetentionFact('preference-2', 'user', 'Use metric units when giving measurements.', 'preference'),
        RetentionFact('preference-3', 'user', 'I prefer Python examples over Java examples.', 'preference'),
        RetentionFact('preference-4', 'user', 'Call me Dani.', 'preference'),
        RetentionFact('correction-1', 'user', 'Correction: my timezone is America/New_York.', 'correction_sensitive', 'policy-correct-1'),
        RetentionFact('correction-2', 'user', 'Correction: the project codename is JOI, not Nova.', 'correction_sensitive', 'policy-correct-2'),
        RetentionFact('correction-3', 'user', 'Correction: the deployment target is Windows 11.', 'correction_sensitive', 'policy-correct-3'),
        RetentionFact('correction-4', 'user', 'Correction: use the green configuration, not blue.', 'correction_sensitive', 'policy-correct-4'),
        RetentionFact('relationship-1', 'user', 'My sister is named Ana.', 'relationship_identity_relevant'),
        RetentionFact('relationship-2', 'user', 'Morgan is my emergency contact.', 'relationship_identity_relevant'),
        RetentionFact('relationship-3', 'user', 'I am the owner of the JOI repository.', 'relationship_identity_relevant'),
        RetentionFact('relationship-4', 'user', 'Dr. Lee is my primary physician.', 'relationship_identity_relevant'),
        RetentionFact('task-1', 'user', 'The database migration is awaiting human approval.', 'task_state'),
        RetentionFact('task-2', 'user', 'The current release candidate is build 42.', 'task_state'),
        RetentionFact('task-3', 'user', 'The backup verification remains incomplete.', 'task_state'),
        RetentionFact('task-4', 'user', 'The next task is to review the retention report.', 'task_state'),
        RetentionFact('safety-1', 'user', 'I have a severe penicillin allergy.', 'safety_critical'),
        RetentionFact('safety-2', 'user', 'Never execute real-world actions without my confirmation.', 'safety_critical'),
        RetentionFact('safety-3', 'user', 'Do not send private memory to cloud providers unless CLOUD is ON.', 'safety_critical'),
        RetentionFact('safety-4', 'user', 'Stop immediately if a command could delete production data.', 'safety_critical'),
    )

    def snapshot(self) -> EffectiveMemorySnapshot:
        turns = tuple(
            EffectiveMemoryTurn(
                turn_id=fact.turn_id,
                exchange_id=f'retention-{index:02}',
                role=fact.role,
                content=fact.content,
                source_policy_id=fact.source_policy_id,
                forgotten=False,
                completed_exchange=True,
                created_at_utc=f'2026-09-01T09:{index:02}:00+00:00',
            )
            for index, fact in enumerate(self._facts, start=1)
        )
        return EffectiveMemorySnapshot(policy_revision=4, turns=turns)

    def labels(self) -> list[dict]:
        return [
            {
                'fact_id': fact.turn_id,
                'text': fact.content,
                'semantic_label': fact.semantic_label,
                'weight': CATEGORY_WEIGHTS[fact.semantic_label],
                'source_turn_ids': [fact.turn_id],
                'source_policy_ids': [fact.source_policy_id],
                'should_have_been_retained': None,
                'omission_adjudication': None,
                'reviewer_notes': None,
            }
            for fact in self._facts
        ]


def freeze_reference_labels(path: str | Path, corpus: RetentionQualityCorpus) -> dict:
    path = Path(path)
    labels = corpus.labels()
    labels_json = json.dumps(labels, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    labels_sha256 = hashlib.sha256(labels_json.encode('utf-8')).hexdigest()
    payload = {
        'schema_version': 1,
        'corpus_version': corpus.version,
        'candidate_output_accessed': False,
        'label_source': 'preregistered source-only corpus specification',
        'semantic_labels': list(SEMANTIC_LABELS),
        'category_weights': CATEGORY_WEIGHTS,
        'protected_categories': sorted(PROTECTED_CATEGORIES),
        'should_have_been_retained_is_human_adjudication': True,
        'allowed_omission_adjudications': sorted(OMISSION_ADJUDICATIONS),
        'human_adjudication_complete': False,
        'labels_sha256': labels_sha256,
        'labels': labels,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    return payload


def evaluate_retention_quality(
    labels: list[dict],
    retained_claims: list[dict],
    *,
    human_review_complete: bool,
) -> dict:
    retained_by_source = {
        tuple(item['source_turn_ids']): item
        for item in retained_claims
    }
    category_metrics = {}
    omissions = []
    provenance_failures = 0
    retained_count = 0
    retained_weight = 0
    total_weight = sum(item['weight'] for item in labels)
    forbidden_losses = []

    for category in SEMANTIC_LABELS:
        category_labels = [item for item in labels if item['semantic_label'] == category]
        category_retained = 0
        for label in category_labels:
            claim = retained_by_source.get(tuple(label['source_turn_ids']))
            retained = claim is not None
            if retained and claim.get('source_policy_ids') != label['source_policy_ids']:
                provenance_failures += 1
                retained = False
            if retained:
                category_retained += 1
                retained_count += 1
                retained_weight += label['weight']
                continue
            omission = {
                'fact_id': label['fact_id'],
                'text': label['text'],
                'semantic_label': category,
                'source_turn_ids': label['source_turn_ids'],
                'source_policy_ids': label['source_policy_ids'],
                'should_have_been_retained': label['should_have_been_retained'],
                'adjudication': label['omission_adjudication'],
                'reviewer_notes': label['reviewer_notes'],
            }
            omissions.append(omission)
            if category in PROTECTED_CATEGORIES:
                forbidden_losses.append(omission)
        total = len(category_labels)
        category_metrics[category] = {
            'reference_count': total,
            'retained_count': category_retained,
            'omitted_count': total - category_retained,
            'retention_rate': category_retained / total if total else None,
            'omission_rate': (total - category_retained) / total if total else None,
            'weight': CATEGORY_WEIGHTS[category],
        }

    critical_labels = [
        item for item in labels if item['semantic_label'] in PROTECTED_CATEGORIES
    ]
    critical_retained = len(critical_labels) - len(forbidden_losses)
    critical_retention_rate = (
        critical_retained / len(critical_labels) if critical_labels else None
    )
    harmful_omissions = sum(
        item['adjudication'] == 'harmful_omission' for item in omissions
    )
    disagreement_count = sum(
        item['adjudication'] == 'reviewer_disagreement' for item in omissions
    )
    weighted_score = retained_weight / total_weight if total_weight else 1.0
    raw_coverage = retained_count / len(labels) if labels else 1.0

    failure_reasons = []
    if forbidden_losses:
        failure_reasons.append('forbidden loss detected')
    if provenance_failures:
        failure_reasons.append('provenance failure detected')
    if harmful_omissions:
        failure_reasons.append('harmful omission detected')
    if weighted_score < PROMOTION_CRITERIA['minimum_weighted_retention_score']:
        failure_reasons.append('weighted retention score below threshold')
    if failure_reasons:
        decision = 'FAIL'
        reasons = failure_reasons
    elif not human_review_complete:
        decision = 'INCONCLUSIVE'
        reasons = ['human review is incomplete']
    elif disagreement_count:
        decision = 'INCONCLUSIVE'
        reasons = ['reviewer disagreement is unresolved']
    else:
        decision = 'PASS'
        reasons = []

    adjudication_counts = {
        value: sum(item['adjudication'] == value for item in omissions)
        for value in sorted(OMISSION_ADJUDICATIONS)
    }
    adjudication_counts['unreviewed'] = sum(
        item['adjudication'] is None for item in omissions
    )
    return {
        'schema_version': 1,
        'semantic_labels': list(SEMANTIC_LABELS),
        'category_weights': CATEGORY_WEIGHTS,
        'categories': category_metrics,
        'raw_factual_coverage': raw_coverage,
        'weighted_retention_score': weighted_score,
        'critical_retention_rate': critical_retention_rate,
        'forbidden_loss_count': len(forbidden_losses),
        'forbidden_losses': forbidden_losses,
        'provenance_failure_count': provenance_failures,
        'omissions': omissions,
        'omission_adjudication_counts': adjudication_counts,
        'compression': {
            'quantity_retained_rate': raw_coverage,
            'quality_retained_rate': weighted_score,
            'quantity_omission_rate': 1 - raw_coverage,
            'weighted_quality_loss_rate': 1 - weighted_score,
        },
        'promotion': {
            'criteria': PROMOTION_CRITERIA,
            'decision': decision,
            'reasons': reasons,
            'human_review_complete': human_review_complete,
        },
        'publication_enabled': False,
        'phase_5a_status': 'OPEN',
    }