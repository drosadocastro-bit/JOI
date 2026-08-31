import argparse
import ctypes
import hashlib
import http.client
import json
import os
import platform
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from compact_memory_benchmark import (
    CORPUS_VERSION,
    REQUIRED_CHECKPOINTS,
    DeterministicCompactCorpus,
)
from config.settings import Settings
from memory.compact_memory import (
    CompactMemoryError,
    ModelCompactMemoryManager,
    ModelCompactSummarizer,
    _bounded_effective_snapshot,
    parse_model_candidate,
)


FROZEN_CORPUS_VERSION = CORPUS_VERSION
DIAGNOSTIC_SCHEMA_VERSION = 1
DEFAULT_MODELS = ('nvidia/nemotron-3-nano', 'qwen/qwen3.5-9b')
DEFAULT_TIMEOUTS = (30,)
RAW_OUTPUT_LIMIT = 16_000
_CONTROL_CHARACTERS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
FROZEN_COMMIT = 'dedf2b8'
FROZEN_EVIDENCE_PATHS = (
    Path('compact_memory_benchmark.py'),
    Path('docs/benchmarks/2026-08-31-nemotron-compact-memory-checkpoints/compact-memory-benchmark.json'),
    Path('docs/benchmarks/2026-08-31-nemotron-compact-memory-checkpoints/compact-memory-benchmark.md'),
    Path('docs/benchmarks/2026-08-31-nemotron-compact-memory-checkpoints/update-reports.json'),
)


class StreamTimeoutError(TimeoutError):
    def __init__(self, message, telemetry):
        super().__init__(message)
        self.telemetry = telemetry


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ('length', ctypes.c_ulong),
        ('memory_load', ctypes.c_ulong),
        ('total_physical', ctypes.c_ulonglong),
        ('available_physical', ctypes.c_ulonglong),
        ('total_page_file', ctypes.c_ulonglong),
        ('available_page_file', ctypes.c_ulonglong),
        ('total_virtual', ctypes.c_ulonglong),
        ('available_virtual', ctypes.c_ulonglong),
        ('available_extended_virtual', ctypes.c_ulonglong),
    ]


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def safe_raw_output(value, max_characters=RAW_OUTPUT_LIMIT):
    return _CONTROL_CHARACTERS.sub('', value)[:max_characters]


def freeze_manifest(paths, commit):
    files = []
    for path in paths:
        path = Path(path)
        files.append({
            'path': path.as_posix(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'size_bytes': path.stat().st_size,
        })
    return {'commit': commit, 'algorithm': 'sha256', 'files': files}


def classify_failure(
    *,
    timeout=False,
    endpoint_available=True,
    parse_error=None,
    validation_error=None,
    state_corrupted=False,
):
    if state_corrupted:
        return 'state_corruption'
    if not endpoint_available:
        return 'endpoint_or_model_unavailable'
    if timeout:
        return 'model_timeout'
    if parse_error:
        return 'malformed_structured_output'
    if validation_error:
        lowered = validation_error.lower()
        if 'unsupported' in lowered:
            return 'unsupported_claim_rejection'
        if 'forgotten' in lowered:
            return 'forgetting_violation'
        if 'stale' in lowered or 'revision' in lowered:
            return 'correction_violation'
        if 'source' in lowered or 'provenance' in lowered:
            return 'provenance_failure'
        return 'candidate_validation_failure'
    return None


def consume_sse_stream(stream, started_at, clock=time.perf_counter, deadline=None):
    content_parts = []
    reasoning_parts = []
    first_token = None
    first_content = None
    usage = {}
    finish_reason = None
    event_count = 0

    def result():
        return {
            'content': ''.join(content_parts),
            'reasoning_content': ''.join(reasoning_parts),
            'time_to_first_token_seconds': first_token,
            'time_to_first_content_seconds': first_content,
            'input_token_count': usage.get('prompt_tokens'),
            'output_token_count': usage.get('completion_tokens'),
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
                    'diagnostic request exceeded its total deadline', result()
                )
            try:
                stream.fp.raw._sock.settimeout(remaining)
            except AttributeError:
                pass
        try:
            line = stream.readline()
        except TimeoutError as exc:
            raise StreamTimeoutError(
                'diagnostic request exceeded its total deadline', result()
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
        reasoning_parts.append(reasoning)
        content_parts.append(content)
    return result()


def _capture_messages(snapshot, model):
    class CaptureBrain:
        messages = None

        def chat(self, messages):
            self.messages = messages
            raise RuntimeError('capture complete')

    brain = CaptureBrain()
    try:
        ModelCompactSummarizer(brain, model)(snapshot)
    except RuntimeError as exc:
        if str(exc) != 'capture complete':
            raise
    return brain.messages


def collect_prompt_burden(snapshot, max_source_characters):
    bounded = _bounded_effective_snapshot(snapshot, max_source_characters)
    effective = [
        turn for turn in bounded.turns
        if not turn.forgotten and turn.content is not None
    ]
    serialized = json.dumps(
        [asdict(turn) for turn in bounded.turns],
        ensure_ascii=True,
        sort_keys=True,
    ).encode('utf-8')
    return {
        'checkpoint_update_count': len(snapshot.turns) // 2,
        'raw_turn_count': len(snapshot.turns),
        'bounded_effective_turn_count': len(effective),
        'candidate_fact_count': len({turn.content.strip() for turn in effective}),
        'correction_count': sum(
            bool(turn.source_policy_id and turn.source_policy_id.startswith('policy-correct-'))
            for turn in snapshot.turns
        ),
        'forgotten_item_count': sum(turn.forgotten for turn in snapshot.turns),
        'effective_source_characters': sum(len(turn.content) for turn in effective),
        'serialized_snapshot_bytes': len(serialized),
        'max_source_characters': max_source_characters,
    }


def _system_cpu_times():
    idle = ctypes.c_ulonglong()
    kernel = ctypes.c_ulonglong()
    user = ctypes.c_ulonglong()
    ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    return idle.value, kernel.value, user.value


def _memory_status():
    status = _MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {'available_ram_bytes': None, 'memory_load_percent': None}
    return {
        'available_ram_bytes': status.available_physical,
        'memory_load_percent': status.memory_load,
    }


class ResourceSampler:
    def __init__(self, interval_seconds=0.5):
        self.interval_seconds = interval_seconds
        self.samples = []
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self):
        previous = _system_cpu_times()
        while not self._stop_event.wait(self.interval_seconds):
            current = _system_cpu_times()
            idle_delta = current[0] - previous[0]
            total_delta = (current[1] - previous[1]) + (current[2] - previous[2])
            cpu_percent = (
                100.0 * (1.0 - idle_delta / total_delta) if total_delta else None
            )
            self.samples.append({
                'elapsed_seconds': len(self.samples) * self.interval_seconds,
                'cpu_percent': cpu_percent,
                **_memory_status(),
            })
            previous = current

    def summary(self):
        cpu = [item['cpu_percent'] for item in self.samples if item['cpu_percent'] is not None]
        ram = [item['available_ram_bytes'] for item in self.samples if item['available_ram_bytes'] is not None]
        return {
            'sample_interval_seconds': self.interval_seconds,
            'sample_count': len(self.samples),
            'cpu_percent_average': sum(cpu) / len(cpu) if cpu else None,
            'cpu_percent_peak': max(cpu) if cpu else None,
            'available_ram_bytes_minimum': min(ram) if ram else None,
            'samples': self.samples,
        }


def _gpu_snapshot():
    if platform.system() != 'Windows':
        return None
    command = (
        "$s=Get-Counter '\\GPU Engine(*)\\Utilization Percentage',"
        "'\\GPU Adapter Memory(*)\\Dedicated Usage',"
        "'\\GPU Adapter Memory(*)\\Shared Usage' -MaxSamples 1 -ErrorAction SilentlyContinue;"
        "$s.CounterSamples|Where-Object CookedValue -gt 0|"
        "Select-Object Path,CookedValue|ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ['powershell.exe', '-NoProfile', '-Command', command],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        )
        payload = json.loads(completed.stdout or 'null')
        return payload if isinstance(payload, list) else [payload] if payload else []
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def _request_stream(base_url, model, messages, timeout_seconds):
    parsed = urllib.parse.urlparse(base_url)
    connection_class = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    connection = connection_class(parsed.hostname, parsed.port, timeout=timeout_seconds)
    payload = json.dumps({
        'model': model,
        'messages': messages,
        'stream': True,
        'stream_options': {'include_usage': True},
    }).encode('utf-8')
    path = f"{parsed.path.rstrip('/')}/chat/completions"
    started = time.perf_counter()
    deadline = started + timeout_seconds
    try:
        connection.request('POST', path, body=payload, headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        if response.status >= 400:
            detail = response.read(4096).decode('utf-8', errors='replace')
            raise RuntimeError(f'LM Studio HTTP {response.status}: {detail}')
        try:
            telemetry = consume_sse_stream(response, started, deadline=deadline)
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


def _model_health(base_url, model):
    try:
        with urllib.request.urlopen(f'{base_url.rstrip("/")}/models', timeout=5) as response:
            payload = json.loads(response.read().decode('utf-8'))
        identifiers = [item.get('id') for item in payload.get('data', [])]
        return {'endpoint_available': True, 'model_visible': model in identifiers, 'visible_models': identifiers}
    except Exception as exc:
        return {'endpoint_available': False, 'model_visible': False, 'error': str(exc)}


def _native_model_metadata(base_url, model):
    root = base_url.rsplit('/v1', 1)[0]
    try:
        with urllib.request.urlopen(f'{root}/api/v1/models', timeout=10) as response:
            payload = json.loads(response.read().decode('utf-8'))
        return next((item for item in payload.get('models', []) if item.get('key') == model), None)
    except Exception:
        return None


def run_trial(base_url, model, snapshot, max_source_characters, timeout_seconds):
    bounded = _bounded_effective_snapshot(snapshot, max_source_characters)
    messages = _capture_messages(bounded, model)
    prompt_json = json.dumps(messages, ensure_ascii=True).encode('utf-8')
    burden = collect_prompt_burden(snapshot, max_source_characters)
    burden['serialized_prompt_bytes'] = len(prompt_json)
    sampler = ResourceSampler()
    gpu_before = _gpu_snapshot()
    sampler.start()
    telemetry = None
    raw_output = ''
    parse_error = None
    validation_error = None
    timeout = False
    request_error = None
    parse_seconds = None
    candidate = None
    try:
        telemetry = _request_stream(base_url, model, messages, timeout_seconds)
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
        timeout = True
        request_error = str(exc)
    except TimeoutError as exc:
        timeout = True
        request_error = str(exc)
    except OSError as exc:
        request_error = str(exc)
    except RuntimeError as exc:
        request_error = str(exc)
    finally:
        sampler.stop()
    gpu_after = _gpu_snapshot()
    accepted = candidate is not None and validation_error is None
    failure_class = classify_failure(
        timeout=timeout,
        parse_error=parse_error,
        validation_error=validation_error,
    )
    if failure_class is None and request_error:
        failure_class = 'request_failure'
    stored_telemetry = dict(telemetry) if telemetry is not None else None
    if stored_telemetry is not None:
        content = stored_telemetry['content']
        reasoning = stored_telemetry['reasoning_content']
        stored_telemetry['content'] = safe_raw_output(content)
        stored_telemetry['reasoning_content'] = safe_raw_output(reasoning)
        stored_telemetry['content_truncated'] = len(content) > RAW_OUTPUT_LIMIT
        stored_telemetry['reasoning_content_truncated'] = len(reasoning) > RAW_OUTPUT_LIMIT
    result = {
        'checkpoint': burden['checkpoint_update_count'],
        'timeout_seconds': timeout_seconds,
        'accepted': accepted,
        'failure_class': failure_class,
        'request_error': request_error,
        'parse_error': parse_error,
        'validation_error': validation_error,
        'prompt_burden': burden,
        'telemetry': stored_telemetry,
        'parse_latency_seconds': parse_seconds,
        'candidate_claim_count': len(candidate.claims) if candidate is not None else 0,
        'raw_rejected_output': safe_raw_output(raw_output) if not accepted and raw_output else None,
        'raw_rejected_output_truncated': len(raw_output) > RAW_OUTPUT_LIMIT,
        'resource_telemetry': {
            **sampler.summary(),
            'gpu_before': gpu_before,
            'gpu_after': gpu_after,
            'gpu_note': 'Windows aggregate counters; adapter and process attribution are not inferred.',
        },
        'publication_attempted': False,
    }
    return result


def run_diagnostics(
    settings,
    output_directory,
    models=DEFAULT_MODELS,
    checkpoints=REQUIRED_CHECKPOINTS,
    timeouts=DEFAULT_TIMEOUTS,
):
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    corpus = DeterministicCompactCorpus()
    runs = []
    for model in models:
        health = _model_health(settings.lmstudio_base_url, model)
        model_run = {
            'model': model,
            'health': health,
            'metadata': _native_model_metadata(settings.lmstudio_base_url, model),
            'trials': [],
        }
        if health['endpoint_available'] and health['model_visible']:
            for timeout_seconds in timeouts:
                for checkpoint in checkpoints:
                    print(
                        f'Diagnosing {model} at {checkpoint} updates, {timeout_seconds}s timeout',
                        flush=True,
                    )
                    model_run['trials'].append(run_trial(
                        settings.lmstudio_base_url,
                        model,
                        corpus.snapshot(checkpoint),
                        settings.compact_memory_max_characters,
                        timeout_seconds,
                    ))
        runs.append(model_run)
    result = {
        'schema_version': DIAGNOSTIC_SCHEMA_VERSION,
        'generated_at_utc': _timestamp(),
        'purpose': 'post-FAIL latency diagnosis; non-promotional',
        'environment': {
            'operating_system': platform.platform(),
            'python_version': platform.python_version(),
            'processor': os.environ.get('PROCESSOR_IDENTIFIER') or platform.processor(),
        },
        'corpus': {
            'version': FROZEN_CORPUS_VERSION,
            'checkpoints': list(checkpoints),
            'max_source_characters': settings.compact_memory_max_characters,
        },
        'generation': {
            'settings': 'LM Studio defaults; stream=true only for telemetry; usage requested',
            'live_prompt_injection_enabled': False,
            'candidate_publication_enabled': False,
        },
        'frozen_baseline': freeze_manifest(FROZEN_EVIDENCE_PATHS, FROZEN_COMMIT),
        'models': runs,
        'acceptance_contract_changed': False,
        'human_review_complete': False,
    }
    json_path = output_directory / 'compact-memory-diagnostics.json'
    json_path.write_text(json.dumps(result, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    _write_markdown(output_directory / 'compact-memory-diagnostics.md', result)
    return result


def _format_metric(value, suffix=''):
    return 'n/a' if value is None else f'{value:.3f}{suffix}'


def _write_markdown(path, result):
    lines = [
        '# Compact Memory Post-FAIL Diagnostics',
        '',
        '**Non-promotional diagnostic evidence. The Phase 5A gate remains open.**',
        '',
        f"- Generated: {result['generated_at_utc']}",
        f"- Corpus: `{result['corpus']['version']}`",
        '- Frozen acceptance contract changed: no',
        '- Live prompt injection: disabled',
        '- Candidate publication: disabled',
        '- Human review: incomplete',
        '',
        '| Model | Updates | Timeout | Result | Failure | TTFT | First content | Total | Output tokens | tok/s | Prompt bytes | Min free RAM |',
        '| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for model in result['models']:
        for trial in model['trials']:
            telemetry = trial['telemetry'] or {}
            resource = trial['resource_telemetry']
            lines.append(
                f"| `{model['model']}` | {trial['checkpoint']} | {trial['timeout_seconds']}s | "
                f"{'accepted' if trial['accepted'] else 'rejected'} | {trial['failure_class'] or 'none'} | "
                f"{_format_metric(telemetry.get('time_to_first_token_seconds'), 's')} | "
                f"{_format_metric(telemetry.get('time_to_first_content_seconds'), 's')} | "
                f"{_format_metric(telemetry.get('total_latency_seconds'), 's')} | "
                f"{telemetry.get('output_token_count', 'n/a')} | "
                f"{_format_metric(telemetry.get('tokens_per_second'))} | "
                f"{trial['prompt_burden']['serialized_prompt_bytes']} | "
                f"{resource['available_ram_bytes_minimum'] or 'n/a'} |"
            )
    lines.extend((
        '',
        '## Interpretation Boundary',
        '',
        'TTFT separates prefill or reasoning delay from visible structured-output delay only when the server emits reasoning events. '
        'Token counts are recorded only when LM Studio returns usage. Resource counters are observational and do not establish causality.',
        '',
        'The frozen benchmark recommendation remains FAIL. These results cannot promote Compact Memory.',
        '',
    ))
    path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Diagnose Compact Memory model latency without publication.')
    parser.add_argument('--output-directory', default='data/logs/compact-memory-diagnostics')
    parser.add_argument('--models', nargs='+', default=list(DEFAULT_MODELS))
    parser.add_argument('--checkpoints', nargs='+', type=int, default=list(REQUIRED_CHECKPOINTS))
    parser.add_argument('--timeouts', nargs='+', type=int, default=list(DEFAULT_TIMEOUTS))
    args = parser.parse_args()
    result = run_diagnostics(
        Settings.load(),
        args.output_directory,
        models=tuple(args.models),
        checkpoints=tuple(args.checkpoints),
        timeouts=tuple(args.timeouts),
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()