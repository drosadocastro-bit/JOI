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

## Phase 2 — Local Voice: Qwen3-TTS
- [x] Verify `qwen/qwen3-1.7b` role (LM Studio identifies it as a text LLM)
- [x] Audio device enumeration
- [x] Explicit PCM WAV capture/playback adapters
- [x] Select `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` for benchmarking
- [ ] Validate selected TTS model on CPU
- [x] Isolated Qwen3-TTS environment
- [x] Benchmark 0.6B first
- [x] English sample
- [ ] Spanish sample
- [ ] Punctuation test
- [ ] Long-text/chunking test
- [ ] Style/emotion instructions
- [ ] Measure first-audio latency
- [x] Measure RAM/VRAM
- [ ] 20-generation soak test
- [ ] Integrate only after benchmark passes

## Phase 3 — Online Voice: ElevenLabs
- [ ] `.env` API credentials
- [ ] ElevenLabs backend
- [ ] Streaming
- [ ] Timeout/error handling
- [ ] Voice router
- [ ] Online -> ElevenLabs
- [ ] Offline/failure -> Qwen3-TTS
- [ ] Preserve session during fallback

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

**Current rule: do not advance beyond Phase 1 until local text-only JOI is stable.**
