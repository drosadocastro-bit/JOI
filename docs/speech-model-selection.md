# Offline Speech Model Selection

Decision date: 2026-08-27

## Selected Models

### Text to speech

- Model: `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
- Package: `qwen-tts==0.1.1`
- Download size: approximately 2.33 GB
- Languages: English, Spanish, and eight others
- License: Apache-2.0
- Reason: smallest released CustomVoice checkpoint, with fixed speakers and
  instruction-based style control. It avoids requiring reference voice audio.

### Speech to text

- Model: `Qwen/Qwen3-ASR-0.6B-hf`
- Runtime: Transformers 5.13 or later
- Download size: approximately 1.47 GB
- Languages: English, Spanish, and 28 others
- License: Apache-2.0
- Reason: smallest released Qwen3-ASR checkpoint, with language detection and
  native Transformers support.

## Runtime Constraints

- The host has 31.2 GB RAM and AMD Ryzen 7000-series graphics with 8 GB VRAM.
- The installed Windows PyTorch build is CPU-only. CUDA, ROCm, vLLM, and
  FlashAttention paths are unavailable.
- Nemotron used approximately 18 GB working-set RAM during Phase 1 acceptance.
- TTS and STT must use separate worker environments because their official
  packages require incompatible Transformers versions.
- Model weights must be downloaded explicitly during setup. Runtime code must
  not download weights or silently use online APIs.
- Initial benchmarks must unload Nemotron before loading a speech model.

## Acceptance Gates

TTS must pass English and Spanish samples, punctuation and long-text tests,
first-audio latency measurement, memory measurement, and a 20-generation soak.

STT must pass English, Spanish, mixed-language, silence, background-noise, and
microphone-device tests. Transcription must remain local and microphone access
must remain explicit.

## Preliminary TTS Benchmark

Measured on the CPU-only host with `qwen-tts==0.1.1`, PyTorch 2.13.0, and a
cache-only model load:

- Model load: 5.151 seconds
- Generation: 16.724 seconds for 3.280 seconds of audio
- Real-time factor: 5.099
- Peak process RSS: 4.713 GiB
- Output: mono 24 kHz PCM-16 WAV

The checkpoint is feasible for local CPU generation, but it is not real-time on
this host. These measurements do not satisfy the full TTS acceptance gates.

## Sources

- https://github.com/QwenLM/Qwen3-TTS
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
- https://github.com/QwenLM/Qwen3-ASR
- https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf