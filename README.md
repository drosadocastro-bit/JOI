# JOI 2.0

Local-first hybrid AI companion experiment.

## Current build

Phase 0/1 scaffold:

- modular architecture
- `.env` configuration
- LM Studio local reasoning brain (`nvidia/nemotron-3-nano`)
- session memory
- terminal UI
- health/status check
- logging
- placeholders for Qwen3-TTS, ElevenLabs, vision, microphone and cloud reasoning

## WSL quick start

```bash
cd ~/JOI_2_0
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
python3 app.py
```

Expected startup:

```text
JOI 2.0
=======
Local Brain: ONLINE
Model:       nvidia/nemotron-3-nano
Voice:       DISABLED
Vision:      OFF
Memory:      SESSION
Cloud:       OFF
```

The default LM Studio endpoint is `http://127.0.0.1:1234/v1`. Edit
`LMSTUDIO_BASE_URL` in `.env` if the server address changes.

`qwen/qwen3-1.7b` is reserved for planned local voice work. TTS and STT are not
active until their audio-specific adapters are implemented and validated.

## Phase 1 acceptance

With LM Studio running and the configured model loaded:

```bash
python phase1_acceptance.py
```

The command runs a 20-turn reliability and context-retention soak, prints
per-turn latency, and writes the report to `data/logs/phase1_acceptance.json`.

To verify outage handling and context preservation across a server restart:

```bash
python phase1_recovery.py
```

This uses LM Studio's `lms` CLI to stop and restart only the local server.

## Invariants

1. Internet is optional.
2. Voice and LLM providers are replaceable.
3. Memory is separate from the LLM context window.
4. Camera and microphone are explicit capabilities and default OFF.
5. Cloud failure must not kill local Joi.
6. Secrets never live in source code.
7. Joi state survives provider changes.
