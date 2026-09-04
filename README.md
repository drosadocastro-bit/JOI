# JOI

<p align="center">
	<img src="docs/assets/JOI2.0.png" width="520" alt="JOI concept art">
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

**Phase 5C: corrective shadow-retrieval evaluation and controlled contextual-usefulness preparation**

JOI now has a stable local text and voice core, append-only episodic memory,
inspectable correction and forgetting, and provider-independent Compact Memory
evaluation. Phase 5A passed its frozen provider-contract and retention-quality
gates. Model-backed Compact Memory remains shadow-only: publication, retrieval,
live prompt injection, and production reliance are not authorized.
Phase 5B's provider-free, default-off graph writer and source-linked
inspection are closed with frozen automatic gates and independent review of all
10 extracted entities passing at 100% precision. Phase 5C's first PPR shadow
retrieval evaluation is preserved as a FAIL because its frozen metric contract
made the threshold unattainable; a corrected v2 contract is frozen but has not
been executed. Controlled contextual retrieval is implemented as a narrow,
disabled-by-default, one-use human-approved path. Its usefulness evaluation is
frozen before responses and ratings; it has not authorized autonomous retrieval
or action. Phase 5D design work is blocked pending executable fixtures,
deterministic receipts, runtime fingerprints, and per-arm human approvals.

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
- feature-flagged local or OpenAI Compact Memory candidates with strict
	structured claims
- provider boundary that leaves memory authority, validation, and persistence
	with JOI
- explicit call-time cloud authorization, trusted HTTPS endpoint enforcement,
	credential redaction, and fail-closed provider behavior
- policy-aware candidate regeneration and machine-readable shadow evaluation
- Luna provider-contract PASS at 25, 50, 100, and 200 updates
- preregistered Retention Quality PASS with completed human adjudication
- 174 passing tests at the Phase 5A closure baseline
- default-off, write-only graph construction from completed exchanges
- deterministic explicit entity candidates, co-occurrence edges, replay
	idempotence, atomic storage, correction/forgetting suppression lineage, and
	source-linked graph inspection
- Phase 5B frozen automatic evaluation PASS with zero unsupported entities,
	full provenance, zero replay inflation, byte-identical replay, and zero
	behavior, prompt, retrieval, provider, or network delta
- Phase 5B human-reviewed extraction precision PASS at 100% across 10 entities
- 239 passing tests at the Phase 5B write-only closure checkpoint
- Phase 5C PPR shadow retrieval v1 FAIL preserved, with a corrected v2 metric
	contract frozen before execution
- controlled contextual retrieval with explicit, one-use human approval,
	effective-source filtering, and no action authorization
- 282 passing tests in the current workspace on 2026-09-04

Still not implemented:

- autonomous or unapproved associative long-term memory retrieval
- speech recognition or push-to-talk
- active vision
- general-purpose cloud reasoning
- runtime voice-mode switching
- streaming LLM tokens into interruptible speech
- production publication or live prompt use of model-backed Compact Memory

## Quick Start

JOI currently targets Python 3.13 on Windows with LM Studio running locally.
The Git repository is `JOI_2_0\JOI_2_0`; the checked-in project expects shared
runtime assets such as virtual environments and model files two levels above it
in the workspace. See [the workspace layout guide](docs/workspace-layout.md)
before changing those paths. Run these commands from the repository root:

```powershell
$workspaceRoot = (Resolve-Path ..\..).Path
& "$workspaceRoot\.venv\Scripts\python.exe" -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Load the configured model in LM Studio and start JOI:

```powershell
lms load nvidia/nemotron-3-nano --identifier nvidia/nemotron-3-nano -y
& "$workspaceRoot\.venv\Scripts\python.exe" app.py
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
& "$workspaceRoot\.venv\Scripts\python.exe" -m venv "$workspaceRoot\.venv-kokoro"
& "$workspaceRoot\.venv-kokoro\Scripts\python.exe" -m pip install kokoro-onnx==0.6.1 soundfile psutil
```

Download the official full-precision `kokoro-v1.0.onnx` and
`voices-v1.0.bin` release assets into `$workspaceRoot\models\kokoro`, then set:

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

ElevenLabs requires deliberate cloud opt-in and a user-scoped Windows DPAPI
credential stored outside the project tree:

```dotenv
VOICE_ENABLED=true
VOICE_MODE=online
CLOUD_ENABLED=true
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

## Provider Credential Protection

- `.env` is non-secret configuration only. Blank legacy key placeholders in
	`.env.example` are ignored by JOI and must never contain values.
- OpenAI and ElevenLabs keys are separate user-scoped Windows DPAPI records
	under `%LOCALAPPDATA%\JOI\credentials`, outside the repository.
- Settings, core state, status, telemetry, JSON, and provider instances do not
	own or retain API keys.
- ElevenLabs credentials may be sent only to the documented HTTPS production
	and residency hosts under `/v1`.
- OpenAI Compact Memory credentials may be sent only to the official HTTPS
	OpenAI `/v1` endpoint and require both startup configuration and call-time
	CLOUD authorization.
- Redirects are refused so the credential-bearing header cannot be forwarded to
	another host.
- Local voice mode does not validate or contact the configured cloud endpoint.

Manage a credential only through hidden prompts:

```powershell
& "$workspaceRoot\.venv\Scripts\python.exe" credential_admin.py
```

Never pass a key as an argument, environment variable, shell command, global
machine setting, or clipboard automation. Rotation and recovery are documented in
[docs/openai-key-rotation-recovery.md](docs/openai-key-rotation-recovery.md).

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
COMPACT_MEMORY_PROVIDER=local
```

`COMPACT_MEMORY_PROVIDER` supports `local` and `openai`. OpenAI additionally
requires `CLOUD_ENABLED=true` and a local `OPENAI_API_KEY`; CLOUD is checked
again at call time. Providers generate candidates and telemetry only. JOI owns
validation, memory state, and persistence. The candidate is stored separately
from the extractive baseline, never enters the live prompt, and accepts only
exact explicit source claims with current turn and policy provenance.
Corrections and logical forgetting enqueue full regeneration from the effective
evidence view. Invalid, unsupported, stale, inferred, or provider-mismatched
claims are rejected before atomic replacement.

Paired baseline/candidate reports are written to
`data/memory/compact-memory-evaluation.json`; the candidate defaults to
`data/memory/compact-memory-model-candidate.json`. Both paths are configurable.
Deterministic drift regression runs at 25, 50, 100, and 200 updates:

```powershell
& "$workspaceRoot\.venv\Scripts\python.exe" -m pytest tests\test_compact_memory_drift.py -q
```

The reproducible real-model benchmark runner uses the same cumulative corpus:

```powershell
& "$workspaceRoot\.venv\Scripts\python.exe" compact_memory_benchmark.py
```

The 2026-08-31 Nemotron run completed all four required checkpoint snapshots
but timed out at each 30-second benchmark limit, accepted no model claims, and
received a **FAIL** recommendation. No hard provenance, resurrection,
unsupported-claim, or state-corruption failure occurred because every candidate
was rejected before publication. See the
[machine-readable result](docs/benchmarks/2026-08-31-nemotron-compact-memory-checkpoints/compact-memory-benchmark.json)
and [concise report](docs/benchmarks/2026-08-31-nemotron-compact-memory-checkpoints/compact-memory-benchmark.md).

Separate streaming diagnostics found that the bounded request was only 7.1-9.2
KB. Nemotron reached reasoning output but no JSON content at every checkpoint;
Qwen3.5-9B also reached no JSON under the same default-on reasoning configuration,
including 120-second non-promotional sensitivity trials. The evidence does not
identify task size as the primary cause. Both measured configurations remain
unsuitable for the 30-second budget. See the
[post-FAIL diagnosis](docs/compact-memory-post-fail-diagnosis.md).

A separate reasoning-OFF experiment verified zero reasoning tokens for both
models without changing the frozen contract. Nemotron reached JSON inside the
budget but produced only malformed candidates; Qwen emitted no full-task token
at any checkpoint. Both models therefore remain rejected, model tuning is
stopped, and the summarizer architecture or provider must be reconsidered. See
the [reasoning-OFF diagnosis](docs/compact-memory-reasoning-off-diagnosis.md).

The rejected local runs remain part of the evidence rather than being erased by
the later cloud result. Under the same frozen 25/50/100/200 contract,
`gpt-5.6-luna` passed with zero malformed candidates, zero unsupported claims,
100% provenance coverage, and 100% correction and forgetting adherence. The
separate preregistered Retention Quality benchmark retained 20 of 24 facts,
scored 100% weighted and critical retention, and recorded zero forbidden losses
or provenance failures. A human reviewer classified all four omitted generic
acknowledgements as acceptable compression.

Phase 5A is formally **PASS with known limitations**, pinned at closure commit
`6628591a0e5d12fb1502f0350c8a5dbd960b2532`. This proves only the behavior under
the frozen corpora, provider, model, schema, and one-trial checkpoint conditions.
It does not prove production readiness, long-horizon drift resistance, broad
human-review generalization, provider-outage recovery, or semantic continuity
across provider switches. Publication and live prompt injection remain disabled.

See the [Phase 5A closure audit](docs/phase-5a-closure-audit.md),
[technical debt register](docs/technical-debt-register.json), and
[final retention-quality report](docs/benchmarks/2026-09-01-retention-quality/luna/retention-quality-final.md).
Phase 5B write-only graph construction and inspection passed their separate
frozen automatic and human-review gates. Phase 5C's original shadow-retrieval
result remains a preserved FAIL; the corrected v2 metric contract is frozen
before execution. The implemented contextual path remains explicitly
human-gated and disabled by default. Live or autonomous memory retrieval,
prompt injection outside that approved path, and production reliance remain
unauthorized. See the [Phase 5C checkpoint](docs/phase-5c.3-closure-record.json),
[controlled contextual retrieval contract](docs/controlled-contextual-retrieval.md),
and [Phase 5D readiness review](docs/phase-5d-execution-readiness-review.json).

Graph writes additionally require persistent mode and explicit opt-in:

```dotenv
ENABLE_GRAPH_MEMORY=false
```

Allowed inspection commands are `/memory graph status`, `/memory graph node
<id>`, `/memory graph recent [limit]`, and `/memory graph why
<node-or-edge-id>`. They do not create a graph read path for conversation.
See the [Phase 5B preregistration](docs/phase-5b-graph-memory-preregistration.md),
[entry authorization](docs/phase-5b-entry-authorization.json), and
[closure record](docs/phase-5b-closure-record.json).

Phase 5B proves only that JOI can construct an inspectable, provenance-linked
associative graph from completed exchanges without changing conversation
behavior. It proves no retrieval quality, factual truth, relational
understanding, identity, authority, production readiness, or NIC wire
compatibility. The graph may encode association. It does not create evidence,
truth, identity, or authority.

## Tests and Acceptance

Run the complete test suite:

```powershell
& "$workspaceRoot\.venv\Scripts\python.exe" -m pytest --tb=short -q
```

Run the Phase 1 conversation soak and restart recovery checks with LM Studio
available:

```powershell
& "$workspaceRoot\.venv\Scripts\python.exe" phase1_acceptance.py
& "$workspaceRoot\.venv\Scripts\python.exe" phase1_recovery.py
```

The controlled local-brain comparison and current model decision are recorded
in [docs/local-brain-model-selection.md](docs/local-brain-model-selection.md).

Speech benchmarks use their isolated environments:

```powershell
& "$workspaceRoot\.venv-tts\Scripts\python.exe" qwen_tts_acceptance.py
& "$workspaceRoot\.venv-kokoro\Scripts\python.exe" kokoro_tts_benchmark.py
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
