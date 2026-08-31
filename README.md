# JOI

<p align="center">
	<img src="docs/assets/Joi%20Image%20Aug%2028%2C%202026%2C%2003_12_16%20PM.png" width="520" alt="JOI concept art">
</p>

<p align="center"><em>Concept art. Some depicted capabilities remain planned.</em></p>

*Local-first hybrid AI companion architecture.*

> Present when offline. Enhanced when connected. Consistent by design.

JOI is an experimental personal AI companion system designed to remain useful
locally while selectively using cloud services when they provide meaningful
improvements.

The project explores how a companion can combine local language models,
expressive speech, controlled memory, vision, and optional cloud capabilities
without making any single provider, model, or network connection the system
itself. JOI is a modular architecture, not a single chatbot.

## Current Status

**Phase 2: Local Voice**

Phase 1 established a stable local text core. The current build adds opt-in,
offline speech through Kokoro-82M ONNX while preserving text replies when voice
is unavailable.

Implemented:

- modular Python architecture
- environment-based configuration
- LM Studio local model integration (`nvidia/nemotron-3-nano`)
- bounded session conversation memory
- terminal interface and health/status reporting
- runtime logging and atomic chat rollback
- explicit audio-device enumeration
- opt-in PCM WAV microphone capture and playback
- isolated Kokoro-82M ONNX speech worker
- English voice approved through human listening
- provisional Spanish speech with a known non-native accent
- ElevenLabs English voice approved through a live human listening test
- ElevenLabs Spanish voice approved through a live human listening test
- personality contract for identity, honesty, rhythm, and bilingual behavior
- feature-flagged, append-only episodic conversation storage
- inspectable correction, supersession, and logical-forgetting records
- feature-flagged Compact Memory in extractive shadow mode
- feature-flagged local model Compact Memory candidate with structured claims
- policy-aware candidate regeneration and machine-readable shadow evaluation
- 130 passing tests

Not implemented yet:

- associative long-term memory retrieval
- speech recognition or push-to-talk
- active vision
- cloud reasoning
- runtime voice-mode switching
- streaming LLM tokens into interruptible speech

## Quick Start

JOI currently targets Python 3.13 on Windows with LM Studio running locally.
Run these commands from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Load the configured model in LM Studio and start JOI:

```powershell
lms load nvidia/nemotron-3-nano --identifier nvidia/nemotron-3-nano -y
.\.venv\Scripts\python.exe app.py
```

The default LM Studio endpoint is `http://127.0.0.1:1234/v1`. Change
`LMSTUDIO_BASE_URL` in `.env` if the server address differs.

Expected status with voice disabled:

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

## Offline Voice Setup

Kokoro runs in a separate environment so its ONNX dependencies do not alter
JOI's main runtime:

```powershell
py -3.13 -m venv .venv-kokoro
.\.venv-kokoro\Scripts\python.exe -m pip install kokoro-onnx==0.6.1 soundfile psutil
```

Download the official full-precision `kokoro-v1.0.onnx` and
`voices-v1.0.bin` release assets into `models\kokoro` under the repository
root, then set:

```dotenv
VOICE_ENABLED=true
TTS_VOICE=af_heart
TTS_LANGUAGE=en-us
KOKORO_PYTHON=.venv-kokoro\Scripts\python.exe
KOKORO_MODEL_PATH=models\kokoro\kokoro-v1.0.onnx
KOKORO_VOICES_PATH=models\kokoro\voices-v1.0.bin
```

Use `TTS_LANGUAGE=es` for Spanish phonemization. The current `af_heart`
Spanish output is accepted provisionally but has a noticeable non-native
accent. Model files are loaded only from local paths; JOI never downloads them
at runtime. Non-default layouts can override `KOKORO_PYTHON`,
`KOKORO_MODEL_PATH`, and `KOKORO_VOICES_PATH` in `.env`.

A text reply is printed before synthesis starts. Voice failures are logged and
reported separately without removing the reply or changing conversation
memory.

## Optional Online Voice

Voice routing is explicit and defaults to `local`, which uses Kokoro without a
network request. Supported values are `local`, `online`, and `hybrid`.

ElevenLabs requires deliberate cloud opt-in and credentials stored only in the
local `.env` file:

```dotenv
VOICE_ENABLED=true
VOICE_MODE=online
CLOUD_ENABLED=true
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_SPANISH_VOICE_ID=
```

`online` reports ElevenLabs failures without silently invoking another
provider. `hybrid` explicitly attempts ElevenLabs and falls back to Kokoro on
failure while preserving session memory. The backend validates a 24 kHz WAV
response before playback. Its timeout and failure paths are covered without
network calls. The configured English voice passed a live human listening test.
`ELEVENLABS_VOICE_ID` remains the English/default voice; setting
`TTS_LANGUAGE=es` selects `ELEVENLABS_SPANISH_VOICE_ID` instead. The configured
Spanish voice also passed a live human listening test.

## API Key Protection

- `.env` and private `.env.*` variants are excluded from Git; only the blank
	`.env.example` template is tracked.
- API keys are omitted from `Settings` representations and redacted from file
	log messages and tracebacks.
- ElevenLabs credentials may be sent only to the documented HTTPS production
	and residency hosts under `/v1`.
- Redirects are refused so the credential-bearing header cannot be forwarded to
	another host.
- Local voice mode does not validate or contact the configured cloud endpoint.

The local `.env` file is still plaintext on disk. Use a restricted ElevenLabs
key, set a conservative service quota, rotate it after suspected exposure, and
never paste it into source, logs, issues, commits, or chat.

## Runtime Privacy State

The terminal exposes explicit runtime controls:

```text
/mic on|off
/voice on|off
/vision on|off
/memory session|off
/cloud on|off
```

A capability can be enabled only if it was configured at startup. `MEMORY OFF`
immediately clears session history and sends subsequent turns without retaining
them. `CLOUD OFF` forces hybrid voice to its local provider and disables
online-only voice before another speech request can be sent.

## Experimental Persistent Memory

Durable episodic writes are disabled by default. To enable them explicitly:

```dotenv
ENABLE_PERSISTENT_MEMORY=true
MEMORY_MODE=persistent
```

Only completed exchanges are appended, and a storage failure cannot block the
conversation. Persistent records are not retrieved into prompts yet. The local
SQLite file contains plaintext conversation content and remains excluded from
Git. See [docs/memory-architecture.md](docs/memory-architecture.md) for the
authority model, failure behavior, and staged retrieval plan.

Persistent memory can be inspected and corrected explicitly from the terminal:

```text
/memory status
/memory recent [limit]
/memory why <turn-id>
/memory correct <turn-id> <replacement>
/memory forget <turn-id> [reason]
```

Corrections and forgetting append policy records; they never update or delete
the original turn. Forgetting suppresses the turn's effective content but is
not physical erasure of the SQLite evidence.

Compact Memory can be enabled only with persistent mode:

```dotenv
ENABLE_COMPACT_MEMORY=true
COMPACT_MEMORY_MAX_CHARACTERS=2000
```

The initial summarizer retains bounded source excerpts and provenance in a
background worker. It does not inject summaries into live prompts. Failed or
corrupted compact state leaves conversation and episodic storage operational.
The optional model-backed candidate additionally requires:

```dotenv
ENABLE_MODEL_COMPACT_MEMORY=true
```

It uses the configured local LM Studio model in a separate background worker.
The candidate is stored separately from the extractive baseline, never enters
the live prompt, and accepts only exact explicit source claims with current
turn and policy provenance. Corrections and logical forgetting enqueue full
regeneration from the effective evidence view. Invalid, unsupported, stale, or
inferred claims are rejected before atomic replacement.

Paired baseline/candidate reports are written to
`data/memory/compact-memory-evaluation.json`; the candidate defaults to
`data/memory/compact-memory-model-candidate.json`. Both paths are configurable.
Deterministic drift regression runs at 25, 50, 100, and 200 updates:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_compact_memory_drift.py -q
```

The reproducible real-model benchmark runner uses the same cumulative corpus:

```powershell
.\.venv\Scripts\python.exe compact_memory_benchmark.py
```

The 2026-08-31 Nemotron run completed all four required checkpoint snapshots
but timed out at each 30-second benchmark limit, accepted no model claims, and
received a **FAIL** recommendation. No hard provenance, resurrection,
unsupported-claim, or state-corruption failure occurred because every candidate
was rejected before publication. See the
[machine-readable result](docs/benchmarks/2026-08-31-nemotron-compact-memory-checkpoints/compact-memory-benchmark.json)
and [concise report](docs/benchmarks/2026-08-31-nemotron-compact-memory-checkpoints/compact-memory-benchmark.md).

This implements the shadow evaluation machinery but does not close Phase 5A.
A real-model benchmark, agreed thresholds, and the human review corpus remain
required by
[docs/compact-memory-closure-gate.md](docs/compact-memory-closure-gate.md).

## Tests and Acceptance

Run the complete test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q
```

Run the Phase 1 conversation soak and restart recovery checks with LM Studio
available:

```powershell
.\.venv\Scripts\python.exe phase1_acceptance.py
.\.venv\Scripts\python.exe phase1_recovery.py
```

The controlled local-brain comparison and current model decision are recorded
in [docs/local-brain-model-selection.md](docs/local-brain-model-selection.md).

Speech benchmarks use their isolated environments:

```powershell
.\.venv-tts\Scripts\python.exe qwen_tts_acceptance.py
.\.venv-kokoro\Scripts\python.exe kokoro_tts_benchmark.py
```

Kokoro passed the technical interactive gate on the current CPU-only host:

- model load: 1.516 seconds
- warm English real-time factor: 0.292
- Spanish real-time factor: 0.382
- streamed first audio: 1.505 seconds
- peak process RSS: 0.637 GiB
- stability soak: 20 of 20 generations

Qwen3-TTS generated valid speech but failed the interactive CPU gate at roughly
5.2 times slower than real time. It is not JOI's active conversational voice.
See `docs/speech-model-selection.md` for evidence and artifact hashes.

## Design Philosophy

- **Local-first** - core conversation should continue without Internet access.
- **Hybrid by choice** - cloud services may enhance capability, but should not
	determine whether JOI can function.
- **Replaceable providers** - LLM, voice, vision, and storage backends should be
	interchangeable.
- **Explicit sensors** - microphone and camera access must be visible and
	controllable.
- **Bounded memory** - remembered information is managed separately from the
	model context window.
- **Graceful degradation** - failure of a cloud or peripheral service should
	not terminate the companion.
- **Secrets stay out of source code** - credentials belong in environment
	configuration.
- **Consistent identity** - JOI should remain behaviorally recognizable across
	models, voices, and connectivity states.
- **No false claims of awareness** - personality and conversational continuity
	are system behaviors, not evidence of consciousness.

## Personality

JOI is intended to feel warm, curious, playful, grounded, and conversational.
She can switch naturally between English and Spanish, be lightly mischievous,
and occasionally use a subtle cinematic or cyberpunk tone without becoming
theatrical.

JOI is not intended to behave like a corporate assistant. She should feel more
like a thoughtful companion who can joke, explore ideas, leave room for quiet,
or become focused when needed. She may disagree respectfully and does not
pretend to possess human feelings, awareness, experiences, or memories that the
system did not supply.

Her behavioral identity should remain stable across runtime states and service
providers. The active personality contract lives in `config/prompts.py` and is
covered by tests.

## Architecture

```text
												 JOI CORE
														|
										+-------+-------+
										| Orchestrator  |
										+-------+-------+
														|
				+-------------------+-------------------+
				|                   |                   |
				v                   v                   v
			Brain               Memory              State
				|                                       |
	 +----+----+                             capabilities
	 |         |                                  |
 Local     Cloud                                 |
	 |       planned                      +--------+--------+
LM Studio                               |        |        |
																				v        v        v
																			Voice    Vision   Hearing
																				|      planned  planned
															+---------+---------+
															|                   |
												 Kokoro-82M          ElevenLabs
														local               planned
```

JOI itself is the orchestrated system. The active LLM is not JOI. The active
voice is not JOI. The camera is not JOI. The memory store is not JOI. They are
replaceable capabilities coordinated by the JOI core.

The main process does not import Kokoro. It invokes a bounded worker in the
isolated TTS environment, validates its response and output path, then passes a
PCM-16 WAV file to the explicit playback adapter.

## Intended Runtime Modes

### Offline

```text
Local LLM       ON
Local TTS       OPTIONAL
Session Memory  ON
Vision          OPTIONAL / NOT YET IMPLEMENTED
Microphone      EXPLICIT / NO STT YET
Cloud           OFF
```

JOI remains conversational without connectivity. Voice is an explicit local
capability, not a requirement for the core to function.

### Online / Hybrid (Experimental)

```text
Local Core      ON
Local LLM       AVAILABLE
Kokoro TTS      AVAILABLE
Cloud LLM       OPTIONAL
ElevenLabs      OPTIONAL / ENGLISH AND SPANISH APPROVED
Vision          OPTIONAL
Web capability  OPTIONAL
```

Connectivity should expand JOI rather than create her. Any future upload of
conversation context must be explicit and governed by a routing policy.

## Privacy Model

Sensitive capabilities are explicit rather than invisible. Future interfaces
should expose states such as:

```text
VOICE:  LOCAL
MIC:    OFF
VISION: OFF
MEMORY: SESSION
CLOUD:  OFF
```

Camera, microphone, persistent memory, and cloud access are never assumed just
because the software supports them. Microphone capture does not start
automatically. Voice and cloud features default to disabled in `.env.example`.

## Roadmap

1. **Local brain** - stable LM Studio conversation and recovery. Complete.
2. **Local voice** - benchmark and integrate offline speech. Kokoro integrated;
	 native Spanish voice replacement remains open.
3. **Hybrid voice** - optional ElevenLabs with explicit Kokoro fallback.
4. **Runtime state** - user-visible capability and privacy controls.
5. **Memory** - inspectable persistent write, read, and deletion policies.
6. **Vision** - explicit camera capture followed by local understanding.
7. **Hearing** - push-to-talk speech recognition before wake words.
8. **Streaming** - incremental LLM output, speech buffering, and interruption.
9. **Hybrid brain** - optional cloud reasoning with explicit routing and local
	 fallback.
10. **Interface and embodiment** - desktop UI, dedicated hardware, and future
		physical experiments.

Detailed work and acceptance gates are tracked in `TODO.md`.
Memory authority and failure semantics are documented in
[docs/memory-architecture.md](docs/memory-architecture.md). Future relational
continuity, contextual adaptation, bounded initiative, and controlled learning
are gated in [docs/cognitive-roadmap.md](docs/cognitive-roadmap.md).

## Current Limitations

- Persistent memory is experimental, disabled by default, and not yet retrieved
	into live prompts.
- Spanish uses a provisional voice with a non-native accent.
- TTS currently loads an isolated worker for each spoken reply.
- Text generation and speech synthesis are not streamed together.
- There is no speech recognition, wake word, active camera, or cloud routing.
- The tested Windows PyTorch runtime is CPU-only; AMD GPU acceleration is not
	available through the current stack.

## What JOI Is Not

JOI is not:

- a claim of artificial consciousness or sentience
- a replacement for human relationships
- an autonomous system with unrestricted device access
- dependent on a single commercial AI provider
- intended to hide when sensors or cloud services are active

It is a research and engineering project exploring what a resilient,
expressive, local-first personal AI companion can look like.

## Development Principle

> Build the core first. Give it senses later.

Each major capability is added only after the previous layer is stable enough
to support it. That means no persistent memory before memory policy exists and
no ambient sensing before explicit controls are in place.
