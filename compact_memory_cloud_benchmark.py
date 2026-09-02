import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from brain.openai_compact_provider import OpenAICompactSummarizerProvider
from compact_memory_benchmark import (
    CORPUS_VERSION,
    REQUIRED_CHECKPOINTS,
    DeterministicCompactCorpus,
    _artifact_bytes,
    _checkpoint_metrics,
    _hard_failure,
)
from config.settings import Settings
from memory.compact_memory import (
    CompactEvaluationStore,
    CompactMemoryEvaluator,
    ModelCompactMemoryManager,
    ModelCompactMemoryStore,
    ProviderBackedCompactSummarizer,
)
from security.credential_provider import CredentialProvider, write_audit_event


def run_cloud_benchmark(
    settings,
    output_directory: str | Path,
    checkpoints=REQUIRED_CHECKPOINTS,
    provider=None,
    credential_provider=None,
    progress=None,
):
    checkpoints = tuple(checkpoints)
    if not checkpoints or tuple(sorted(set(checkpoints))) != checkpoints:
        raise ValueError('checkpoints must be unique and increasing')
    if checkpoints[-1] > 200:
        raise ValueError('the deterministic corpus supports at most 200 updates')
    if not settings.cloud_enabled:
        raise ValueError('cloud benchmark requires CLOUD_ENABLED=true')
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    if credential_provider is None:
        credential_provider = CredentialProvider(
            audit_sink=lambda event: write_audit_event(
                settings.credential_audit_path,
                event,
            ),
        )
    provider = provider or OpenAICompactSummarizerProvider(
        credential_provider=credential_provider,
        model=settings.openai_model,
        cloud_authorized=lambda: settings.cloud_enabled,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    health = provider.health()
    if not health.get('ok'):
        raise RuntimeError(f'provider unavailable: {health.get("error", "health check failed")}')

    candidate_path = output_directory / 'model-candidate.json'
    report_path = output_directory / 'update-reports.json'
    summarizer = ProviderBackedCompactSummarizer(provider)
    manager = ModelCompactMemoryManager(
        ModelCompactMemoryStore(candidate_path),
        summarizer,
    )
    evaluator = CompactMemoryEvaluator(
        manager,
        CompactEvaluationStore(report_path),
        max_source_characters=settings.compact_memory_max_characters,
    )
    corpus = DeterministicCompactCorpus()
    reports = []
    checkpoint_results = []
    hard_failures = []

    for update in checkpoints:
        snapshot = corpus.snapshot(update)
        previous_bytes = _artifact_bytes(candidate_path)
        report = evaluator.update(snapshot, checkpoint=update)
        reports.append(report)
        failure = _hard_failure(report, snapshot, candidate_path, previous_bytes)
        metrics = _checkpoint_metrics(update, reports)
        generation = summarizer.last_generation
        metrics.update({
            'provider': generation.provider if generation else None,
            'model': generation.model if generation else None,
            'time_to_first_token_seconds': (
                generation.time_to_first_token_seconds if generation else None
            ),
            'input_tokens': generation.input_tokens if generation else None,
            'output_tokens': generation.output_tokens if generation else None,
            'estimated_cost_usd': generation.estimated_cost_usd if generation else None,
        })
        checkpoint_results.append(metrics)
        if progress is not None:
            progress(update, report, generation)
        if failure is not None:
            hard_failures.append({'update': update, 'reason': failure})
            break
        if not report.accepted:
            break

    completed_updates = checkpoint_results[-1]['update_count'] if checkpoint_results else 0
    candidate_failures = [
        {'update': report.checkpoint, 'reason': report.rejection_reason}
        for report in reports
        if not report.accepted
    ]
    recommendation = (
        'PASS'
        if completed_updates == checkpoints[-1]
        and len(checkpoint_results) == len(checkpoints)
        and not candidate_failures
        and not hard_failures
        else 'FAIL'
    )
    result = {
        'schema_version': 1,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'frozen_baseline_commit': '8f004a7',
        'environment': {
            'operating_system': platform.platform(),
            'python_version': platform.python_version(),
        },
        'provider': {
            'identifier': provider.provider_id,
            'model': provider.model_id,
            'endpoint': settings.openai_base_url,
            'structured_outputs': bool(health.get('structured_outputs')),
            'reasoning_effort': 'none',
            'request_timeout_seconds': settings.openai_timeout_seconds,
        },
        'corpus': {
            'identifier': 'joi-compact-memory-deterministic',
            'version': CORPUS_VERSION,
            'requested_checkpoints': list(checkpoints),
            'completed_updates': completed_updates,
            'execution_mode': 'independent cumulative checkpoint snapshots',
            'trials_per_checkpoint': 1,
            'max_source_characters': settings.compact_memory_max_characters,
        },
        'checkpoints': checkpoint_results,
        'candidate_failures': candidate_failures,
        'hard_failures': hard_failures,
        'recommendation': recommendation,
        'publication_enabled': False,
        'live_prompt_injection_enabled': False,
        'human_review_complete': False,
        'phase_5a_status': 'OPEN',
    }
    _write_artifacts(output_directory, result)
    return result


def _write_artifacts(output_directory: Path, result: dict) -> None:
    (output_directory / 'cloud-benchmark.json').write_text(
        json.dumps(result, ensure_ascii=True, indent=2) + '\n',
        encoding='utf-8',
    )
    rows = [
        '| Updates | Accepted | Coverage | Provenance | Input | Output | Cost USD | Latency | TTFT |',
        '| ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for item in result['checkpoints']:
        ttft = item['time_to_first_token_seconds']
        rows.append(
            f"| {item['update_count']} | "
            f"{'yes' if not item['failed_or_malformed_candidate_count'] else 'no'} | "
            f"{item['factual_coverage']:.3f} | {item['provenance_coverage']:.3f} | "
            f"{item['input_tokens'] if item['input_tokens'] is not None else 'null'} | "
            f"{item['output_tokens'] if item['output_tokens'] is not None else 'null'} | "
            f"{item['estimated_cost_usd'] if item['estimated_cost_usd'] is not None else 'null'} | "
            f"{item['average_summarization_latency_seconds']:.3f}s | "
            f"{f'{ttft:.3f}s' if ttft is not None else 'null'} |"
        )
    markdown = '\n'.join([
        '# OpenAI Compact Memory Shadow Benchmark',
        '',
        f"**Recommendation: {result['recommendation']}**",
        '',
        f"- Provider: `{result['provider']['identifier']}`",
        f"- Model: `{result['provider']['model']}`",
        f"- Frozen baseline commit: `{result['frozen_baseline_commit']}`",
        '- Publication: disabled',
        '- Human review: incomplete',
        '- Phase 5A: open',
        '',
        '## Checkpoints',
        '',
        *rows,
        '',
        'Missing provider telemetry is recorded as `null`; it is never inferred.',
        '',
    ])
    (output_directory / 'cloud-benchmark.md').write_text(markdown, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(
        description='Run the OpenAI Compact Memory shadow benchmark.',
    )
    parser.add_argument(
        '--output-directory',
        default='docs/benchmarks/2026-08-31-openai-compact-memory',
    )
    args = parser.parse_args()
    settings = Settings.load()

    def print_progress(update, report, generation):
        status = 'accepted' if report.accepted else f'rejected: {report.rejection_reason}'
        cost = generation.estimated_cost_usd if generation else None
        print(f'Update {update:03}: {report.latency_seconds:.3f}s, cost={cost} - {status}', flush=True)

    result = run_cloud_benchmark(settings, args.output_directory, progress=print_progress)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['recommendation'] == 'PASS' else 1)


if __name__ == '__main__':
    main()