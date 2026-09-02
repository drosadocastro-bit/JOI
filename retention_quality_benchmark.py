import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from brain.openai_compact_provider import OpenAICompactSummarizerProvider
from config.settings import Settings
from memory.compact_memory import (
    ModelCompactMemoryManager,
    ModelCompactMemoryStore,
    ProviderBackedCompactSummarizer,
    parse_model_candidate,
)
from memory.retention_quality import (
    OMISSION_ADJUDICATIONS,
    PROMOTION_CRITERIA,
    RetentionQualityCorpus,
    evaluate_retention_quality,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_labels_sha256(labels: list[dict]) -> str:
    encoded = json.dumps(
        labels,
        ensure_ascii=True,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _verify_preregistration(
    labels_path: Path,
    preregistration_path: Path,
    implementation_path: Path,
) -> tuple[dict, dict]:
    preregistration = json.loads(preregistration_path.read_text(encoding='utf-8'))
    labels_payload = json.loads(labels_path.read_text(encoding='utf-8'))
    blind = preregistration['blind_label_protocol']
    execution = preregistration['execution_contract']
    if not blind.get('labels_frozen_before_candidate_generation'):
        raise RuntimeError('reference labels were not frozen before generation')
    if labels_payload.get('candidate_output_accessed') is not False:
        raise RuntimeError('reference labels were not produced blind to candidate output')
    if _sha256(labels_path) != blind['reference_labels_file_sha256']:
        raise RuntimeError('reference label file hash mismatch')
    canonical_hash = _canonical_labels_sha256(labels_payload['labels'])
    if canonical_hash != blind['canonical_labels_sha256']:
        raise RuntimeError('canonical reference label hash mismatch')
    if _sha256(implementation_path) != execution['compact_memory_implementation_sha256']:
        raise RuntimeError('Compact Memory prompt/schema implementation changed')
    if execution.get('publication_enabled') is not False:
        raise RuntimeError('publication must remain disabled')
    if execution.get('phase_5a_status') != 'OPEN':
        raise RuntimeError('Phase 5A must remain open')
    registered_criteria = preregistration['promotion_criteria']
    for name, value in PROMOTION_CRITERIA.items():
        if name == 'systematic_critical_omission_rule':
            continue
        if registered_criteria.get(name) != value:
            raise RuntimeError(f'promotion criterion changed: {name}')
    return preregistration, labels_payload


def run_retention_quality_benchmark(
    *,
    output_directory: str | Path,
    labels_path: str | Path,
    preregistration_path: str | Path,
    implementation_path: str | Path,
    provider,
) -> dict:
    output_directory = Path(output_directory)
    labels_path = Path(labels_path)
    preregistration_path = Path(preregistration_path)
    implementation_path = Path(implementation_path)
    preregistration, labels_payload = _verify_preregistration(
        labels_path,
        preregistration_path,
        implementation_path,
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    summarizer = ProviderBackedCompactSummarizer(provider)
    manager = ModelCompactMemoryManager(
        ModelCompactMemoryStore(output_directory / 'model-candidate.json'),
        summarizer,
    )
    candidate = manager.update(RetentionQualityCorpus().snapshot())
    retained_claims = [
        {
            **asdict(claim),
            'source_turn_ids': list(claim.source_turn_ids),
            'source_policy_ids': list(claim.source_policy_ids),
        }
        for claim in candidate.claims
    ]
    quality = evaluate_retention_quality(
        labels_payload['labels'],
        retained_claims,
        human_review_complete=False,
    )
    generation = summarizer.last_generation
    report = {
        'schema_version': 1,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'benchmark': preregistration['benchmark'],
        'preregistration_file_sha256': _sha256(preregistration_path),
        'reference_labels_file_sha256': _sha256(labels_path),
        'candidate_generation_count': 1,
        'prompt_or_schema_changed_after_opening_results': False,
        'provider': {
            'identifier': generation.provider,
            'model': generation.model,
            'input_tokens': generation.input_tokens,
            'output_tokens': generation.output_tokens,
            'estimated_cost_usd': generation.estimated_cost_usd,
            'total_latency_seconds': generation.total_latency_seconds,
            'time_to_first_token_seconds': generation.time_to_first_token_seconds,
        },
        'retention_quality': quality,
        'raw_factual_coverage_is_secondary': True,
        'publication_enabled': False,
        'human_review_complete': False,
        'phase_5a_status': 'OPEN',
    }
    _write_report_artifacts(output_directory, report)
    return report


def rebuild_retention_quality_report(
    output_directory: str | Path,
    labels_path: str | Path,
) -> dict:
    output_directory = Path(output_directory)
    labels_payload = json.loads(Path(labels_path).read_text(encoding='utf-8'))
    candidate = parse_model_candidate(
        (output_directory / 'model-candidate.json').read_text(encoding='utf-8')
    )
    retained_claims = [
        {
            **asdict(claim),
            'source_turn_ids': list(claim.source_turn_ids),
            'source_policy_ids': list(claim.source_policy_ids),
        }
        for claim in candidate.claims
    ]
    report_path = output_directory / 'retention-quality-report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['retention_quality'] = evaluate_retention_quality(
        labels_payload['labels'],
        retained_claims,
        human_review_complete=False,
    )
    _write_report_artifacts(output_directory, report)
    return report


def validate_human_review(review: dict, frozen_omissions: list[dict]) -> dict[str, dict]:
    if review.get('human_review_complete') is not True:
        raise RuntimeError('human review is not marked complete')
    reviewed = review.get('omissions')
    if not isinstance(reviewed, list):
        raise RuntimeError('human review omissions must be a list')
    frozen_by_id = {item['fact_id']: item for item in frozen_omissions}
    reviewed_by_id = {item.get('fact_id'): item for item in reviewed}
    if len(reviewed_by_id) != len(reviewed) or set(reviewed_by_id) != set(frozen_by_id):
        raise RuntimeError('human review does not match frozen omissions')
    immutable_fields = (
        'fact_id',
        'text',
        'semantic_label',
        'source_turn_ids',
        'source_policy_ids',
    )
    for fact_id, item in reviewed_by_id.items():
        frozen = frozen_by_id[fact_id]
        if any(item.get(field) != frozen.get(field) for field in immutable_fields):
            raise RuntimeError('human review does not match frozen omissions')
        if not isinstance(item.get('should_have_been_retained'), bool):
            raise RuntimeError('human review retention flags must be boolean')
        adjudication = item.get('adjudication')
        if adjudication not in OMISSION_ADJUDICATIONS:
            raise RuntimeError('human review contains an invalid adjudication')
        notes = item.get('reviewer_notes')
        if not isinstance(notes, str) or not notes.strip():
            raise RuntimeError('human review requires reviewer notes')
        if item['should_have_been_retained'] and adjudication in {
            'acceptable_compression', 'redundant_information',
        }:
            raise RuntimeError('human review retention flag conflicts with adjudication')
        if not item['should_have_been_retained'] and adjudication == 'harmful_omission':
            raise RuntimeError('human review retention flag conflicts with adjudication')
    return reviewed_by_id


def finalize_human_review(
    output_directory: str | Path,
    labels_path: str | Path,
    review_path: str | Path,
) -> dict:
    output_directory = Path(output_directory)
    automatic_report = json.loads(
        (output_directory / 'retention-quality-report.json').read_text(encoding='utf-8')
    )
    review = json.loads(Path(review_path).read_text(encoding='utf-8'))
    reviewed_by_id = validate_human_review(
        review,
        automatic_report['retention_quality']['omissions'],
    )
    labels_payload = json.loads(Path(labels_path).read_text(encoding='utf-8'))
    reviewed_labels = []
    for label in labels_payload['labels']:
        reviewed_label = dict(label)
        adjudication = reviewed_by_id.get(label['fact_id'])
        if adjudication is not None:
            reviewed_label['should_have_been_retained'] = adjudication[
                'should_have_been_retained'
            ]
            reviewed_label['omission_adjudication'] = adjudication['adjudication']
            reviewed_label['reviewer_notes'] = adjudication['reviewer_notes']
        reviewed_labels.append(reviewed_label)
    candidate = parse_model_candidate(
        (output_directory / 'model-candidate.json').read_text(encoding='utf-8')
    )
    retained_claims = [
        {
            **asdict(claim),
            'source_turn_ids': list(claim.source_turn_ids),
            'source_policy_ids': list(claim.source_policy_ids),
        }
        for claim in candidate.claims
    ]
    final_report = {
        **automatic_report,
        'finalized_at_utc': datetime.now(timezone.utc).isoformat(),
        'human_review_file_sha256': _sha256(Path(review_path)),
        'retention_quality': evaluate_retention_quality(
            reviewed_labels,
            retained_claims,
            human_review_complete=True,
        ),
        'human_review_complete': True,
        'publication_enabled': False,
        'phase_5a_status': 'OPEN',
    }
    (output_directory / 'retention-quality-final.json').write_text(
        json.dumps(final_report, ensure_ascii=True, indent=2) + '\n',
        encoding='utf-8',
    )
    _write_markdown(
        output_directory,
        final_report,
        filename='retention-quality-final.md',
    )
    return final_report


def _write_report_artifacts(output_directory: Path, report: dict) -> None:
    quality = report['retention_quality']
    (output_directory / 'retention-quality-report.json').write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + '\n',
        encoding='utf-8',
    )
    review_template = {
        'schema_version': 1,
        'instructions': (
            'For each omission, set should_have_been_retained to true or false, '
            'choose one allowed adjudication, and add reviewer notes.'
        ),
        'allowed_adjudications': sorted(OMISSION_ADJUDICATIONS),
        'human_review_complete': False,
        'omissions': quality['omissions'],
    }
    (output_directory / 'human-review-template.json').write_text(
        json.dumps(review_template, ensure_ascii=True, indent=2) + '\n',
        encoding='utf-8',
    )
    _write_markdown(output_directory, report)


def _write_markdown(
    output_directory: Path,
    report: dict,
    filename: str = 'retention-quality-report.md',
) -> None:
    quality = report['retention_quality']
    rows = [
        '| Category | Weight | Reference | Retained | Omitted | Retention | Omission |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for category, metrics in quality['categories'].items():
        rows.append(
            f"| {category} | {metrics['weight']} | {metrics['reference_count']} | "
            f"{metrics['retained_count']} | {metrics['omitted_count']} | "
            f"{metrics['retention_rate']:.3f} | {metrics['omission_rate']:.3f} |"
        )
    markdown = '\n'.join([
        '# Compact Memory Retention Quality Benchmark',
        '',
        f"**Decision: {quality['promotion']['decision']}**",
        '',
        f"- Weighted retention score: {quality['weighted_retention_score']:.3f}",
        f"- Critical retention rate: {quality['critical_retention_rate']:.3f}",
        f"- Forbidden losses: {quality['forbidden_loss_count']}",
        f"- Raw factual coverage (secondary): {quality['raw_factual_coverage']:.3f}",
        '- Publication: disabled',
        f"- Human review: {'complete' if report['human_review_complete'] else 'incomplete'}",
        '- Phase 5A: open',
        '',
        '## Category Results',
        '',
        *rows,
        '',
        '## Compression Quality',
        '',
        f"- Quantity retained: {quality['compression']['quantity_retained_rate']:.3f}",
        f"- Weighted quality retained: {quality['compression']['quality_retained_rate']:.3f}",
        '',
        (
            'Omission classifications were completed by a human reviewer.'
            if report['human_review_complete'] else
            'Omission classifications remain unreviewed until a human completes the review template.'
        ),
        '',
    ])
    (output_directory / filename).write_text(
        markdown,
        encoding='utf-8',
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run the preregistered Compact Memory retention-quality benchmark.',
    )
    parser.add_argument(
        '--output-directory',
        default='docs/benchmarks/2026-09-01-retention-quality/luna',
    )
    parser.add_argument(
        '--labels',
        default='docs/benchmarks/2026-09-01-retention-quality/reference-labels.json',
    )
    parser.add_argument(
        '--preregistration',
        default='docs/benchmarks/2026-09-01-retention-quality/preregistration.json',
    )
    parser.add_argument('--rebuild-from-candidate', action='store_true')
    parser.add_argument('--finalize-human-review', action='store_true')
    parser.add_argument(
        '--human-review',
        default='docs/benchmarks/2026-09-01-retention-quality/luna/human-review.json',
    )
    args = parser.parse_args()
    if args.finalize_human_review:
        report = finalize_human_review(
            args.output_directory,
            args.labels,
            args.human_review,
        )
        print(json.dumps(report, indent=2))
        return
    if args.rebuild_from_candidate:
        report = rebuild_retention_quality_report(args.output_directory, args.labels)
        print(json.dumps(report, indent=2))
        return
    settings = Settings.load()
    if not settings.cloud_enabled:
        raise SystemExit('CLOUD must be ON')
    from security.credential_provider import CredentialProvider, write_audit_event

    credential_provider = CredentialProvider(
        audit_sink=lambda event: write_audit_event(
            settings.credential_audit_path,
            event,
        ),
    )
    provider = OpenAICompactSummarizerProvider(
        credential_provider=credential_provider,
        model=settings.openai_model,
        cloud_authorized=lambda: settings.cloud_enabled,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    report = run_retention_quality_benchmark(
        output_directory=args.output_directory,
        labels_path=args.labels,
        preregistration_path=args.preregistration,
        implementation_path='memory/compact_memory.py',
        provider=provider,
    )
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()