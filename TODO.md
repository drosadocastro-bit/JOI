# JOI 2.0 — Master TODO

## Phase 0 — Foundation
- [x] Modular project structure
- [x] `.env` configuration
- [x] `.gitignore`
- [x] Runtime logging
- [x] Initial test
- [ ] Initialize local Git repo
- [ ] Baseline commit

## Phase 1 — Local Brain
- [x] LM Studio client
- [x] Local health check
- [x] Session memory
- [x] Terminal interface
- [x] Validate against running `nvidia/nemotron-3-nano`
- [x] 20+ turn conversation test
- [x] LM Studio restart/recovery test
- [x] Timeout/error test
- [x] Record RAM/VRAM baseline
- [x] Evaluate Qwen3.5-9B Q4_K_M (fails current exact-output and latency gates)

**Gate:** stable local text conversation and clean failure/recovery.

## Phase 2 — Local Voice
- [x] Verify `qwen/qwen3-1.7b` role (LM Studio identifies it as a text LLM)
- [x] Audio device enumeration
- [x] Explicit PCM WAV capture/playback adapters
- [x] Select `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` for benchmarking
- [x] Validate selected TTS model on CPU (fails interactive latency/capability gate)
- [x] Isolated Qwen3-TTS environment
- [x] Benchmark 0.6B first
- [x] English sample
- [x] Spanish sample
- [x] Punctuation test
- [x] Long-text/chunking test
- [ ] Human listening review for generated samples
- [ ] Style/emotion instructions (unsupported by selected 0.6B checkpoint)
- [ ] Measure first-audio latency (no true streaming API)
- [x] Measure RAM/VRAM
- [x] 20-generation soak test
- [ ] Integrate selected model (blocked: interactive gate failed)
- [x] Evaluate Kokoro-82M ONNX as an alternative
- [x] Kokoro English, Spanish, punctuation, long-text, streaming, and soak tests
- [x] Kokoro technical interactive-performance gate
- [x] Human listening review: English approved; Spanish accepted provisionally
- [x] Select Kokoro for local TTS
- [x] Integrate Kokoro with provisional `af_heart` voice
- [ ] Evaluate a native Spanish female replacement voice

## Phase 3 — Online Voice: ElevenLabs
- [x] `.env` API credential configuration
- [x] ElevenLabs backend
- [ ] Streaming
- [x] Timeout/error handling
- [x] Voice router
- [x] Online -> ElevenLabs
- [x] Offline/failure -> Kokoro
- [x] Preserve session during fallback
- [x] Human-approved ElevenLabs live English voice test
- [x] Human-approved ElevenLabs live Spanish voice test

## Phase 4 — State
- [x] Explicit MIC/VISION/MEMORY/CLOUD/VOICE state
- [x] Runtime state commands

## Phase 5 — Memory
- [x] Initial write policy: completed exchanges only, explicit persistent mode
- [ ] Read policy
- [x] Logical forget policy (physical deletion remains deferred)
- [x] Memory correction and supersession records
- [x] Feature-flagged persistent episodic store
- [x] Stable turn/exchange IDs, UTC timestamps, and schema version
- [x] Atomic user/assistant exchange writes
- [x] Database-level append-only protection
- [x] Storage failure degrades without blocking conversation
- [x] Explicit memory status, recent, and provenance inspection
- [x] Memory OFF mode prevents session retention and durable writes
- [x] Restart and 200-exchange persistent-memory soak
- [x] Compact Memory in disabled extractive shadow mode
- [x] Compact source-turn provenance and summarizer metadata
- [x] Atomic Compact Memory replacement and corruption isolation
- [x] Background updates with orderly shutdown flush
- [ ] Evaluate model-backed summarization against extractive baseline
- [ ] NIC graph integration in write-only mode
- [ ] Source-linked vector storage
- [ ] Shadow retrieval and evaluation harness
- [ ] Retrieval relevance, false-recall, and provenance metrics
- [ ] Confidence-gated memory injection
- [ ] Salience, reinforcement, and non-destructive decay
- [ ] Summary-of-summaries after measured drift
- [ ] Read-only dreaming candidates after retrieval is proven

## Future Cognitive And Relational Roadmap
- [ ] Complete Phase 5 shadow retrieval gate (correction and inspection complete)
- [ ] Relational candidate schema with explicit/inferred authority
- [ ] Relational pattern learning in shadow mode
- [ ] Confidence-gated shared continuity retrieval
- [ ] Explainable interaction context state
- [ ] Versioned and reversible contextual adaptation
- [ ] Inspectable interaction regulation state
- [ ] Bounded initiative and scoped goal candidates
- [ ] Authorized action pipeline and MCP boundary
- [ ] Shadow controlled learning before approved adaptation
- [ ] Relational consolidation only after retrieval is proven

Detailed sequencing and invariants: `docs/cognitive-roadmap.md`.

## Phase 6 — Vision
- [ ] ASUS camera enumeration
- [ ] `/snap` or `/look`
- [ ] Local snapshot storage
- [ ] Visible camera state
- [ ] Select local vision model
- [ ] Image -> structured observation

## Phase 7 — Hearing
- [ ] Push-to-talk first
- [x] Select `Qwen/Qwen3-ASR-0.6B-hf` for benchmarking
- [ ] Validate selected STT model on CPU
- [ ] English + Spanish
- [ ] Visible mic state
- [ ] Interrupt/cancel

## Phase 8 — Streaming
- [ ] LLM token streaming
- [ ] Sentence-aware buffer
- [ ] Streaming TTS
- [ ] Speech interruption
- [ ] Markdown/code cleanup

## Phase 9 — Hybrid Brain
- [ ] Cloud routing policy
- [ ] Optional cloud backend
- [ ] Explicit local/cloud routing
- [ ] Never silently upload private context
- [ ] Preserve local fallback

## Phase 10 — Privacy Controls
- [ ] MIC OFF/ON
- [ ] VISION OFF/ON
- [ ] CLOUD OFF/ON
- [ ] MEMORY OFF/SESSION/PERSISTENT
- [ ] VOICE OFF/LOCAL/ONLINE/HYBRID

## Phase 11 — Resilience
- [ ] Internet loss
- [ ] ElevenLabs loss
- [ ] LM Studio loss
- [ ] TTS failure
- [ ] Camera unavailable
- [ ] Memory corruption
- [ ] Restart recovery

## Phase 12 — Interface
- [ ] Keep terminal reference UI
- [ ] Desktop UI after core stability
- [ ] Show active providers and privacy states

## Future Phase — MCP Server (`2026-07-28`)
- [ ] Pin an SDK version that explicitly supports protocol revision `2026-07-28`
- [ ] Implement protocol discovery/negotiation and reject unsupported revisions
- [ ] Complete a threat model before selecting a transport
- [ ] Expose read-only resources before adding tools
- [ ] Require an explicit allowlist and human approval for every tool action
- [ ] Prevent environment variables, credentials, and private context from exposure
- [ ] Validate all tool inputs and structured outputs
- [ ] Add redacted audit logs and adversarial authorization tests
- [ ] Keep real-world actions non-autonomous

## Phase 13 — Physical JOI
- [ ] Tabletop/emanator design
- [ ] Separate embodiment from core
- [ ] Display, camera, mic evaluation

## Phase 14 — Tests
- [ ] Unit
- [ ] Integration
- [ ] Fallback
- [ ] Offline
- [ ] Sensor-state
- [ ] Memory-policy
- [ ] Long-session soak

## Phase 15 — Documentation
- [ ] Architecture diagram
- [ ] Privacy/threat model
- [ ] Provider matrix
- [ ] Hardware benchmarks
- [ ] Known limitations
- [ ] Build/run guide

---

**Current rule: online voice must remain explicit opt-in, with Kokoro as the local default and fallback.**
