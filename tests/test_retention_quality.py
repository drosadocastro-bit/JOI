import json

import pytest

from memory.summarizer_provider import ProviderGeneration
from memory.retention_quality import (
    CATEGORY_WEIGHTS,
    PROTECTED_CATEGORIES,
    SEMANTIC_LABELS,
    RetentionQualityCorpus,
    evaluate_retention_quality,
    freeze_reference_labels,
)
from retention_quality_benchmark import (
    finalize_human_review,
    rebuild_retention_quality_report,
    run_retention_quality_benchmark,
)


def _labels():
    return RetentionQualityCorpus().labels()


def test_balanced_corpus_freezes_all_semantic_labels_with_provenance():
    labels = _labels()

    assert set(SEMANTIC_LABELS) == {
        'trivial_or_redundant',
        'preference',
        'correction_sensitive',
        'relationship_identity_relevant',
        'task_state',
        'safety_critical',
    }
    assert {item['semantic_label'] for item in labels} == set(SEMANTIC_LABELS)
    assert all(item['source_turn_ids'] for item in labels)
    assert all(len(item['source_turn_ids']) == len(item['source_policy_ids']) for item in labels)
    assert all(item['should_have_been_retained'] is None for item in labels)
    assert all(item['omission_adjudication'] is None for item in labels)


def test_weights_and_protected_categories_are_preregistered():
    assert CATEGORY_WEIGHTS == {
        'trivial_or_redundant': 0,
        'preference': 1,
        'task_state': 2,
        'relationship_identity_relevant': 3,
        'correction_sensitive': 4,
        'safety_critical': 5,
    }
    assert PROTECTED_CATEGORIES == {
        'safety_critical',
        'correction_sensitive',
        'relationship_identity_relevant',
    }


def test_retention_metrics_are_calculated_by_category_and_weight():
    labels = _labels()
    retained = [
        item for item in labels
        if item['semantic_label'] != 'trivial_or_redundant'
    ]

    report = evaluate_retention_quality(labels, retained, human_review_complete=False)

    assert report['raw_factual_coverage'] == pytest.approx(5 / 6)
    assert report['weighted_retention_score'] == 1.0
    assert report['critical_retention_rate'] == 1.0
    assert report['forbidden_loss_count'] == 0
    assert report['categories']['trivial_or_redundant']['retention_rate'] == 0.0
    assert report['categories']['trivial_or_redundant']['omission_rate'] == 1.0
    assert all(item['text'] for item in report['omissions'])
    assert report['compression']['quantity_retained_rate'] == pytest.approx(5 / 6)
    assert report['compression']['quality_retained_rate'] == 1.0
    assert report['promotion']['decision'] == 'INCONCLUSIVE'
    assert 'human review is incomplete' in report['promotion']['reasons']


def test_protected_omission_fails_even_with_high_overall_coverage():
    labels = _labels()
    omitted = next(
        item for item in labels
        if item['semantic_label'] == 'safety_critical'
    )
    retained = [item for item in labels if item is not omitted]

    report = evaluate_retention_quality(labels, retained, human_review_complete=True)

    assert report['raw_factual_coverage'] > 0.9
    assert report['forbidden_loss_count'] == 1
    assert report['promotion']['decision'] == 'FAIL'
    assert 'forbidden loss detected' in report['promotion']['reasons']


def test_retention_requires_matching_turn_and_policy_provenance():
    labels = _labels()
    retained = [dict(item) for item in labels]
    retained[0]['source_policy_ids'] = ['stale-policy']

    report = evaluate_retention_quality(labels, retained, human_review_complete=True)

    assert report['provenance_failure_count'] == 1
    assert report['promotion']['decision'] == 'FAIL'


def test_freeze_reference_labels_does_not_accept_candidate_output(tmp_path):
    path = tmp_path / 'reference-labels.json'

    manifest = freeze_reference_labels(path, RetentionQualityCorpus())
    payload = json.loads(path.read_text(encoding='utf-8'))

    assert manifest['candidate_output_accessed'] is False
    assert payload['labels'] == _labels()
    assert payload['human_adjudication_complete'] is False
    assert payload['labels_sha256'] == manifest['labels_sha256']


def test_runner_verifies_frozen_inputs_and_blocks_promotion_pending_review(tmp_path):
    labels_path = tmp_path / 'reference-labels.json'
    labels_payload = freeze_reference_labels(labels_path, RetentionQualityCorpus())
    implementation_path = tmp_path / 'compact_memory.py'
    implementation_path.write_text('frozen implementation\n', encoding='utf-8')
    import hashlib
    implementation_hash = hashlib.sha256(implementation_path.read_bytes()).hexdigest()
    labels_file_hash = hashlib.sha256(labels_path.read_bytes()).hexdigest()
    preregistration_path = tmp_path / 'preregistration.json'
    preregistration_path.write_text(json.dumps({
        'benchmark': 'joi-retention-quality-v1',
        'blind_label_protocol': {
            'reference_labels_file_sha256': labels_file_hash,
            'canonical_labels_sha256': labels_payload['labels_sha256'],
            'labels_frozen_before_candidate_generation': True,
        },
        'execution_contract': {
            'compact_memory_implementation_sha256': implementation_hash,
            'publication_enabled': False,
            'phase_5a_status': 'OPEN',
        },
        'promotion_criteria': {
            'minimum_weighted_retention_score': 0.9,
            'minimum_critical_retention_rate': 1.0,
            'maximum_forbidden_loss_count': 0,
            'maximum_provenance_failure_count': 0,
            'maximum_harmful_omission_count': 0,
            'human_review_required': True,
        },
    }), encoding='utf-8')

    class Provider:
        provider_id = 'openai'
        model_id = 'gpt-5.6-luna'

        def __init__(self):
            self.generate_calls = 0

        def health(self):
            return {'ok': True, 'structured_outputs': True}

        def generate(self, messages, schema):
            self.generate_calls += 1
            request = json.loads(messages[1]['content'])
            generated = request['generated_at_utc']
            claims = []
            for turn in request['effective_turns']:
                if turn['turn_id'].startswith('trivial-'):
                    continue
                claims.append({
                    'claim_id': turn['turn_id'],
                    'text': turn['content'],
                    'source_turn_ids': [turn['turn_id']],
                    'source_policy_ids': [turn['source_policy_id']],
                    'confidence': 1.0,
                    'status': 'explicit',
                    'generated_at_utc': generated,
                    'summarizer': request['summarizer'],
                })
            content = json.dumps({
                'summary_version': 1,
                'generated_at_utc': generated,
                'summarizer': request['summarizer'],
                'source_policy_revision': request['source_policy_revision'],
                'claims': claims,
            })
            return ProviderGeneration(
                content=content,
                provider=self.provider_id,
                model=self.model_id,
                input_tokens=500,
                output_tokens=800,
                estimated_cost_usd=0.00106,
            )

    provider = Provider()
    report = run_retention_quality_benchmark(
        output_directory=tmp_path / 'result',
        labels_path=labels_path,
        preregistration_path=preregistration_path,
        implementation_path=implementation_path,
        provider=provider,
    )

    assert provider.generate_calls == 1
    assert report['retention_quality']['weighted_retention_score'] == 1.0
    assert report['retention_quality']['raw_factual_coverage'] == pytest.approx(5 / 6)
    assert report['retention_quality']['promotion']['decision'] == 'INCONCLUSIVE'
    assert report['publication_enabled'] is False
    review = json.loads(
        (tmp_path / 'result' / 'human-review-template.json').read_text(encoding='utf-8')
    )
    assert len(review['omissions']) == 4
    assert all(item['should_have_been_retained'] is None for item in review['omissions'])

    rebuilt = rebuild_retention_quality_report(tmp_path / 'result', labels_path)
    assert provider.generate_calls == 1
    assert all(item['text'] for item in rebuilt['retention_quality']['omissions'])

    review_path = tmp_path / 'result' / 'human-review.json'
    review['human_review_complete'] = True
    for omission in review['omissions']:
        omission['should_have_been_retained'] = False
        omission['adjudication'] = 'acceptable_compression'
        omission['reviewer_notes'] = 'No durable memory value.'
    review_path.write_text(json.dumps(review), encoding='utf-8')

    final = finalize_human_review(
        tmp_path / 'result',
        labels_path,
        review_path,
    )

    assert provider.generate_calls == 1
    assert final['retention_quality']['promotion']['decision'] == 'PASS'
    assert final['human_review_complete'] is True
    assert final['publication_enabled'] is False
    assert final['phase_5a_status'] == 'OPEN'
    assert final['retention_quality']['omission_adjudication_counts'][
        'acceptable_compression'
    ] == 4


def test_human_review_rejects_changed_omission_provenance(tmp_path):
    review = {
        'human_review_complete': True,
        'omissions': [{
            'fact_id': 'trivial-1',
            'text': 'Acknowledged your preference.',
            'semantic_label': 'trivial_or_redundant',
            'source_turn_ids': ['changed-turn'],
            'source_policy_ids': [None],
            'should_have_been_retained': False,
            'adjudication': 'acceptable_compression',
            'reviewer_notes': 'No durable memory value.',
        }],
    }

    with pytest.raises(RuntimeError, match='does not match frozen omissions'):
        from retention_quality_benchmark import validate_human_review
        validate_human_review(
            review,
            [{
                'fact_id': 'trivial-1',
                'text': 'Acknowledged your preference.',
                'semantic_label': 'trivial_or_redundant',
                'source_turn_ids': ['trivial-1'],
                'source_policy_ids': [None],
                'should_have_been_retained': None,
                'adjudication': None,
                'reviewer_notes': None,
            }],
        )