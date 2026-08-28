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
- [ ] Record RAM/VRAM baseline

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
- [ ] Explicit MIC/VISION/MEMORY/CLOUD/VOICE state
- [ ] Runtime state commands

## Phase 5 — Memory
- [ ] Write policy
- [ ] Read policy
- [ ] Forget/delete policy
- [ ] Persistent store
- [ ] Memory inspection
- [ ] Memory OFF mode

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
