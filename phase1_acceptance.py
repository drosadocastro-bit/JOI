import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from brain.local_llm import LocalLMStudioBrain
from config.settings import Settings
from core.router import BrainRouter
from memory.session_memory import SessionMemory


def percentile(values, fraction):
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def run_acceptance(turns):
    settings = Settings.load()
    brain = LocalLMStudioBrain(
        settings.lmstudio_base_url,
        settings.local_model,
        settings.request_timeout_seconds,
    )
    health = brain.health()
    if not health.get('ok'):
        raise RuntimeError(f"LM Studio is unavailable: {health.get('error', 'unknown error')}")
    if not health.get('selected_model_visible'):
        raise RuntimeError(f"Configured model is not visible: {settings.local_model}")

    router = BrainRouter(brain)
    memory = SessionMemory(
        'You are running a reliability test. Answer briefly and follow exact-output instructions.',
    )
    marker = 'NOVA-27'
    latencies = []
    failures = []

    for turn in range(1, turns + 1):
        if turn == 1:
            prompt = f'Remember the marker {marker}. Reply with exactly TURN 1 OK.'
        elif turn == turns:
            prompt = 'Reply with only the marker you were asked to remember in turn 1.'
        else:
            prompt = f'Reply with exactly TURN {turn} OK.'

        previous_messages = memory.snapshot()
        memory.add_user(prompt)
        started = time.perf_counter()
        try:
            reply = router.chat(memory.snapshot())
        except Exception as exc:
            memory.messages = previous_messages
            failures.append({'turn': turn, 'error': str(exc)})
            print(f'Turn {turn:02}: FAIL - {exc}', flush=True)
            continue
        latency = time.perf_counter() - started
        latencies.append(latency)
        memory.add_assistant(reply)

        expected = marker if turn == turns else f'TURN {turn} OK'
        exact = reply.strip() == expected
        if not exact:
            failures.append({'turn': turn, 'expected': expected, 'actual': reply.strip()})
        print(f'Turn {turn:02}: {latency:6.2f}s - {"PASS" if exact else "MISMATCH"}', flush=True)

    report = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'endpoint': settings.lmstudio_base_url,
        'model': settings.local_model,
        'requested_turns': turns,
        'completed_turns': len(latencies),
        'failures': failures,
        'memory_messages': len(memory.snapshot()),
        'memory_limit': memory.max_messages,
        'latency_seconds': {
            'minimum': round(min(latencies), 3) if latencies else None,
            'median': round(statistics.median(latencies), 3) if latencies else None,
            'p95': round(percentile(latencies, 0.95), 3) if latencies else None,
            'maximum': round(max(latencies), 3) if latencies else None,
            'total': round(sum(latencies), 3),
        },
        'passed': len(latencies) == turns and not failures and len(memory.snapshot()) <= memory.max_messages,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description='Run the live JOI Phase 1 acceptance soak.')
    parser.add_argument('--turns', type=int, default=20)
    parser.add_argument('--output', default='data/logs/phase1_acceptance.json')
    args = parser.parse_args()
    if args.turns < 2:
        parser.error('--turns must be at least 2')

    report = run_acceptance(args.turns)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()