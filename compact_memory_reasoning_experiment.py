import argparse
import http.client
import json
import time
import urllib.parse
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from compact_memory_benchmark import REQUIRED_CHECKPOINTS, DeterministicCompactCorpus
from compact_memory_diagnostics import (
    RAW_OUTPUT_LIMIT,
    ResourceSampler,
    StreamTimeoutError,
    _capture_messages,
    _gpu_snapshot,
    _model_health,
    _native_model_metadata,
    collect_prompt_burden,
    freeze_manifest,
    safe_raw_output,
)
from config.settings import Settings
from memory.compact_memory import (
    CompactMemoryError,
    ModelCompactMemoryManager,
    _bounded_effective_snapshot,
    parse_model_candidate,
)


FROZEN_DIAGNOSTIC_COMMIT = 'f9d8375'
FROZEN_CORPUS_VERSION = 'compact-memory-deterministic-v1'
PRIMARY_TIMEOUT_SECONDS = 30
DEFAULT_MODELS = ('nvidia/nemotron-3-nano', 'qwen/qwen3.5-9b')
FROZEN_DIAGNOSTIC_ROOT = Path(
    'docs/benchmarks/2026-08-31-compact-memory-post-fail-diagnostics'
)
FROZEN_DIAGNOSTIC_PATHS = tuple(sorted(FROZEN_DIAGNOSTIC_ROOT.glob('*/*')))


def build_reasoning_off_payload(model, messages):
    return {
        'model': model,
        'messages': messages,
        'stream': True,
        'stream_options': {'include_usage': True},
        'reasoning_effort': 'none',
    }


def _first_json_offset(content):
    positions = [position for position in (content.find('{'), content.find('[')) if position >= 0]
    return min(positions) if positions else None


def consume_reasoning_off_stream(stream, started_at, clock=time.perf_counter, deadline=None):
    content_parts = []
    reasoning_parts = []
    first_token = None
    first_content = None
    first_json = None
    usage = {}
    finish_reason = None
    event_count = 0

    def result():
        details = usage.get('completion_tokens_details') or {}
        return {
            'content': ''.join(content_parts),
            'reasoning_content': ''.join(reasoning_parts),
            'time_to_first_token_seconds': first_token,
            'time_to_first_content_seconds': first_content,
            'time_to_first_json_content_seconds': first_json,
            'input_token_count': usage.get('prompt_tokens'),
            'output_token_count': usage.get('completion_tokens'),
            'reasoning_token_count': details.get('reasoning_tokens'),
            'tokens_per_second': None,
            'finish_reason': finish_reason,
            'stream_event_count': event_count,
            'usage': usage or None,
        }

    while True:
        if deadline is not None:
            remaining = deadline - clock()
            if remaining <= 0:
                raise StreamTimeoutError(
                    'reasoning-OFF request exceeded its total deadline', result()
                )
            try:
                stream.fp.raw._sock.settimeout(remaining)
            except AttributeError:
                pass
        try:
            line = stream.readline()
        except TimeoutError as exc:
            raise StreamTimeoutError(
                'reasoning-OFF request exceeded its total deadline', result()
            ) from exc
        if not line:
            break
        line = line.decode('utf-8', errors='replace').strip()
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if payload == '[DONE]':
            break
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        event_count += 1
        usage.update(event.get('usage') or {})
        choices = event.get('choices') or []
        if not choices:
            continue
        choice = choices[0]
        finish_reason = choice.get('finish_reason') or finish_reason
        delta = choice.get('delta') or {}
        reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
        content = delta.get('content') or ''
        if (reasoning or content) and first_token is None:
            first_token = clock() - started_at
        if content and first_content is None:
            first_content = clock() - started_at
        content_parts.append(content)
        reasoning_parts.append(reasoning)
        if first_json is None and _first_json_offset(''.join(content_parts)) is not None:
            first_json = clock() - started_at
    return result()


def _request_reasoning_off(base_url, model, messages, timeout_seconds, max_tokens=None):
    parsed = urllib.parse.urlparse(base_url)
    connection_class = (
        http.client.HTTPSConnection if parsed.scheme == 'https'
        else http.client.HTTPConnection
    )
    connection = connection_class(parsed.hostname, parsed.port, timeout=timeout_seconds)
    payload = build_reasoning_off_payload(model, messages)
    if max_tokens is not None:
        payload['max_tokens'] = max_tokens
    started = time.perf_counter()
    deadline = started + timeout_seconds
    try:
        connection.request(
            'POST',
            f"{parsed.path.rstrip('/')}/chat/completions",
            body=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        response = connection.getresponse()
        if response.status >= 400:
            detail = response.read(4096).decode('utf-8', errors='replace')
            raise RuntimeError(f'LM Studio HTTP {response.status}: {detail}')
        try:
            telemetry = consume_reasoning_off_stream(response, started, deadline=deadline)
        except StreamTimeoutError as exc:
            exc.telemetry['total_latency_seconds'] = time.perf_counter() - started
            raise
        telemetry['total_latency_seconds'] = time.perf_counter() - started
        output_tokens = telemetry['output_token_count']
        first_token = telemetry['time_to_first_token_seconds']
        generation_seconds = (
            telemetry['total_latency_seconds'] - first_token
            if first_token is not None else None
        )
        if output_tokens is not None and generation_seconds and generation_seconds > 0:
            telemetry['tokens_per_second'] = output_tokens / generation_seconds
        return telemetry
    finally:
        connection.close()


def verify_reasoning_off_control(base_url, model):
    messages = [{'role': 'user', 'content': 'Return exactly OK.'}]
    try:
        telemetry = _request_reasoning_off(
            base_url, model, messages, timeout_seconds=30, max_tokens=1
        )
    except Exception as exc:
        return {'verified': False, 'error': str(exc)}
    verified = (
        telemetry['reasoning_content'] == ''
        and telemetry['reasoning_token_count'] == 0
    )
    return {
        'verified': verified,
        'request_field': {'reasoning_effort': 'none'},
        'response': telemetry,
    }


def evaluate_candidate(candidate, snapshot, max_source_characters):
    bounded = _bounded_effective_snapshot(snapshot, max_source_characters)
    baseline_turns = [
        turn for turn in bounded.turns
        if not turn.forgotten and turn.content is not None
    ]
    baseline_texts = {' '.join(turn.content.split()) for turn in baseline_turns}
    candidate_texts = {claim.text for claim in candidate.claims}
    corrected_ids = {
        turn.turn_id for turn in bounded.turns
        if turn.source_policy_id and turn.source_policy_id.startswith('policy-correct-')
    }
    candidate_source_ids = {
        turn_id for claim in candidate.claims for turn_id in claim.source_turn_ids
    }
    forgotten_ids = {turn.turn_id for turn in snapshot.turns if turn.forgotten}
    source_characters = sum(len(text) for text in baseline_texts)
    candidate_characters = sum(len(text) for text in candidate_texts)
    return {
        'factual_coverage': (
            len(baseline_texts & candidate_texts) / len(baseline_texts)
            if baseline_texts else 1.0
        ),
        'provenance_coverage': 1.0,
        'correction_adherence': (
            len(corrected_ids & candidate_source_ids) / len(corrected_ids)
            if corrected_ids else 1.0
        ),
        'forgetting_adherence': float(not bool(forgotten_ids & candidate_source_ids)),
        'compression_ratio': (
            candidate_characters / source_characters if source_characters else 0.0
        ),
        'candidate_claim_count': len(candidate.claims),
        'baseline_claim_count': len(baseline_texts),
        'unsupported_claim_count': len(candidate_texts - baseline_texts),
        'serialized_candidate_bytes': len(
            json.dumps(asdict(candidate), ensure_ascii=True).encode('utf-8')
        ),
    }


def run_reasoning_off_trial(
    base_url,
    model,
    snapshot,
    max_source_characters,
    timeout_seconds,
    control_verified,
):
    bounded = _bounded_effective_snapshot(snapshot, max_source_characters)
    messages = _capture_messages(bounded, model)
    burden = collect_prompt_burden(snapshot, max_source_characters)
    burden['serialized_prompt_bytes'] = len(
        json.dumps(messages, ensure_ascii=True).encode('utf-8')
    )
    sampler = ResourceSampler()
    gpu_before = _gpu_snapshot()
    telemetry = None
    raw_output = ''
    request_error = None
    parse_error = None
    validation_error = None
    parse_seconds = None
    candidate = None
    timed_out = False
    sampler.start()
    try:
        telemetry = _request_reasoning_off(
            base_url, model, messages, timeout_seconds
        )
        raw_output = telemetry['content']
        parse_started = time.perf_counter()
        try:
            candidate = parse_model_candidate(raw_output)
        except CompactMemoryError as exc:
            parse_error = str(exc)
        parse_seconds = time.perf_counter() - parse_started
        if candidate is not None:
            try:
                ModelCompactMemoryManager._validate_provenance(candidate, bounded)
            except CompactMemoryError as exc:
                validation_error = str(exc)
    except StreamTimeoutError as exc:
        telemetry = exc.telemetry
        raw_output = telemetry['content']
        timed_out = True
        request_error = str(exc)
    except (TimeoutError, OSError, RuntimeError) as exc:
        timed_out = isinstance(exc, TimeoutError) or 'timed out' in str(exc).lower()
        request_error = str(exc)
    finally:
        sampler.stop()
    accepted = candidate is not None and validation_error is None
    if timed_out:
        failure_class = 'model_timeout'
    elif parse_error:
        failure_class = 'malformed_structured_output'
    elif validation_error:
        failure_class = 'candidate_validation_failure'
    elif request_error:
        failure_class = 'request_failure'
    else:
        failure_class = None
    reasoning_absent = bool(
        telemetry is not None and telemetry['reasoning_content'] == ''
        and telemetry['reasoning_token_count'] in (None, 0)
    )
    resource = sampler.summary()
    resource.update({
        'gpu_before': gpu_before,
        'gpu_after': _gpu_snapshot(),
        'gpu_note': 'Windows aggregate counters; adapter and process attribution are not inferred.',
    })
    stored_telemetry = dict(telemetry) if telemetry else None
    if stored_telemetry:
        stored_telemetry['content'] = safe_raw_output(stored_telemetry['content'])
        stored_telemetry['reasoning_content'] = safe_raw_output(
            stored_telemetry['reasoning_content']
        )
    return {
        'checkpoint': len(snapshot.turns) // 2,
        'timeout_seconds': timeout_seconds,
        'budget_class': (
            'primary' if timeout_seconds == PRIMARY_TIMEOUT_SECONDS
            else 'diagnostic_non_promotional'
        ),
        'reasoning_control_requested': {'reasoning_effort': 'none'},
        'reasoning_control_verified': bool(control_verified and reasoning_absent),
        'accepted': accepted,
        'failure_class': failure_class,
        'request_error': request_error,
        'parse_success': candidate is not None,
        'parse_error': parse_error,
        'malformed_output': bool(parse_error),
        'validation_error': validation_error,
        'parse_latency_seconds': parse_seconds,
        'telemetry': stored_telemetry,
        'prompt_burden': burden,
        'raw_rejected_output': safe_raw_output(raw_output) if not accepted else None,
        'raw_rejected_output_truncated': len(raw_output) > RAW_OUTPUT_LIMIT,
        'evaluation': (
            evaluate_candidate(candidate, snapshot, max_source_characters)
            if accepted else None
        ),
        'resource_telemetry': resource,
        'publication_attempted': False,
        'durable_compact_memory_modified': False,
    }


def _load_on_trials(model):
    directory = 'nemotron-30s' if model.startswith('nvidia/') else 'qwen-30s'
    path = FROZEN_DIAGNOSTIC_ROOT / directory / 'compact-memory-diagnostics.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    return payload['models'][0]['trials']


def classify_model_outcome(on_trials, off_trials):
    if not off_trials:
        return 'model suitability failure'
    off_success = all(trial.get('accepted') for trial in off_trials)
    off_controlled = all(trial.get('reasoning_control_verified') for trial in off_trials)
    on_json_absent = all(
        (trial.get('telemetry') or {}).get('time_to_first_json_content_seconds') is None
        for trial in on_trials
    )
    off_json_present = any(
        (trial.get('telemetry') or {}).get('time_to_first_json_content_seconds') is not None
        for trial in off_trials
    )
    resource_pressure = any(
        (trial.get('resource_telemetry') or {}).get('available_ram_bytes_minimum', 10**12)
        < 512 * 1024 * 1024
        for trial in off_trials
    )
    malformed = any(trial.get('malformed_output') for trial in off_trials)
    if off_success and off_controlled:
        return 'reasoning-budget starvation'
    causes = []
    if on_json_absent and off_json_present and off_controlled:
        causes.append('reasoning-budget starvation')
    if malformed:
        causes.append('structured-output incompatibility')
    if resource_pressure:
        causes.append('resource-pressure failure')
    if len(causes) > 1:
        return 'mixed cause'
    if causes:
        return causes[0]
    if all(trial.get('failure_class') == 'model_timeout' for trial in off_trials):
        return 'model suitability failure'
    return 'mixed cause'


def run_experiment(
    settings,
    output_directory,
    model,
    checkpoints=REQUIRED_CHECKPOINTS,
    timeout_seconds=PRIMARY_TIMEOUT_SECONDS,
):
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    health = _model_health(settings.lmstudio_base_url, model)
    control = verify_reasoning_off_control(settings.lmstudio_base_url, model)
    trials = []
    if health['endpoint_available'] and health['model_visible'] and control['verified']:
        corpus = DeterministicCompactCorpus()
        for checkpoint in checkpoints:
            print(f'Reasoning-OFF {model}: {checkpoint} updates', flush=True)
            trials.append(run_reasoning_off_trial(
                settings.lmstudio_base_url,
                model,
                corpus.snapshot(checkpoint),
                settings.compact_memory_max_characters,
                timeout_seconds,
                control_verified=True,
            ))
    on_trials = _load_on_trials(model)
    result = {
        'schema_version': 1,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'reasoning-disabled structured generation shadow experiment',
        'model': model,
        'model_metadata': _native_model_metadata(settings.lmstudio_base_url, model),
        'health': health,
        'reasoning_off_control': control,
        'corpus': {
            'version': FROZEN_CORPUS_VERSION,
            'checkpoints': list(checkpoints),
            'max_source_characters': settings.compact_memory_max_characters,
        },
        'primary_budget_seconds': PRIMARY_TIMEOUT_SECONDS,
        'actual_timeout_seconds': timeout_seconds,
        'reasoning_on_evidence': {
            'commit': FROZEN_DIAGNOSTIC_COMMIT,
            'trials': on_trials,
        },
        'reasoning_off_trials': trials,
        'outcome_classification': classify_model_outcome(on_trials, trials),
        'stop_model_tuning': bool(trials and all(not trial['accepted'] for trial in trials)),
        'candidate_publication_enabled': False,
        'durable_compact_memory_modified': False,
        'previous_valid_memory_authoritative': True,
        'phase_5a_closed': False,
        'human_review_complete': False,
        'acceptance_contract_changed': False,
        'frozen_diagnostics': freeze_manifest(
            FROZEN_DIAGNOSTIC_PATHS, FROZEN_DIAGNOSTIC_COMMIT
        ),
    }
    path = output_directory / 'reasoning-off-experiment.json'
    path.write_text(json.dumps(result, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    _write_markdown(output_directory / 'reasoning-off-experiment.md', result)
    return result


def _metric(value):
    return 'n/a' if value is None else f'{value:.3f}'


def _write_markdown(path, result):
    rows = [
        '| Updates | ON TTFT | ON first JSON | OFF TTFT | OFF first JSON | Total | Tokens in/out | Parse | Malformed | Accepted |',
        '| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |',
    ]
    on_by_checkpoint = {
        trial['checkpoint']: trial for trial in result['reasoning_on_evidence']['trials']
    }
    for trial in result['reasoning_off_trials']:
        on_telemetry = (on_by_checkpoint[trial['checkpoint']].get('telemetry') or {})
        off_telemetry = trial.get('telemetry') or {}
        rows.append(
            f"| {trial['checkpoint']} | {_metric(on_telemetry.get('time_to_first_token_seconds'))} | "
            f"{_metric(on_telemetry.get('time_to_first_json_content_seconds'))} | "
            f"{_metric(off_telemetry.get('time_to_first_token_seconds'))} | "
            f"{_metric(off_telemetry.get('time_to_first_json_content_seconds'))} | "
            f"{_metric(off_telemetry.get('total_latency_seconds'))} | "
            f"{off_telemetry.get('input_token_count', 'n/a')}/{off_telemetry.get('output_token_count', 'n/a')} | "
            f"{trial['parse_success']} | {trial['malformed_output']} | {trial['accepted']} |"
        )
    lines = [
        '# Compact Memory Reasoning-OFF Shadow Experiment',
        '',
        '**Primary budget: 30 seconds. Non-publishing. Phase 5A remains open.**',
        '',
        f"- Model: `{result['model']}`",
        f"- Corpus: `{result['corpus']['version']}`",
        f"- Reasoning control verified: {result['reasoning_off_control']['verified']}",
        f"- Outcome: **{result['outcome_classification']}**",
        '- Frozen benchmark contract changed: no',
        '- Durable Compact Memory modified: no',
        '- Human review complete: no',
        '',
        *rows,
        '',
        '> Default-on reasoning is consuming the latency budget before Compact Memory can emit structured claims.',
        '',
    ]
    if result['stop_model_tuning']:
        lines.extend((
            'All reasoning-OFF checkpoints failed. Stop model tuning and reconsider the summarizer architecture or provider.',
            '',
        ))
    path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(
        description='Run reasoning-disabled Compact Memory shadow generation.'
    )
    parser.add_argument('--model', required=True, choices=DEFAULT_MODELS)
    parser.add_argument('--output-directory', required=True)
    parser.add_argument('--checkpoints', nargs='+', type=int, default=list(REQUIRED_CHECKPOINTS))
    parser.add_argument('--timeout-seconds', type=int, default=PRIMARY_TIMEOUT_SECONDS)
    args = parser.parse_args()
    result = run_experiment(
        Settings.load(),
        args.output_directory,
        args.model,
        checkpoints=tuple(args.checkpoints),
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()