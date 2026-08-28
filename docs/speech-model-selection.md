# Offline Speech Model Selection

Decision date: 2026-08-27

## Selected Models

### Initial text-to-speech candidate

- Model: `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
- Package: `qwen-tts==0.1.1`
- Download size: approximately 2.33 GB
- Languages: English, Spanish, and eight others
- License: Apache-2.0
- Reason: smallest released CustomVoice checkpoint with fixed speakers. It
  avoids requiring reference voice audio.

### Leading text-to-speech candidate

- Model: `Kokoro-82M` v1.0 ONNX, full precision
- Runtime: `kokoro-onnx==0.6.1`
- Model size: 325,505,369 bytes plus 28,214,398 bytes for voices
- Languages tested: American English (`af_heart`) and Spanish (`ef_dora`)
- License: Apache-2.0 weights, MIT runtime
- Reason: CPU-native ONNX inference, real streaming API, low memory use, and
  substantially faster-than-real-time generation on this host

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

### Acceptance run

The cache-only acceptance runner completed 24 generations on 2026-08-28:

- Model load: 9.773 seconds
- Full suite: 751.185 seconds
- Peak process RSS: 4.372 GiB
- English, Spanish, and punctuation samples: generated successfully
- Long text: generated as three sentence-aware chunks
- Stability soak: 20 of 20 generations completed
- Artifacts: 24 nonempty mono 24 kHz PCM-16 WAV files
- Total generated audio: 140.160 seconds

Structural validation does not establish pronunciation or voice quality. The
English, Spanish, punctuation, and long-text artifacts still require human
listening before integration is approved.

The selected 0.6B implementation explicitly discards the `instruct` argument,
so style or emotion instructions cannot be accepted with this checkpoint. Its
streaming flag only simulates streaming input and returns audio after generation;
true first-audio latency cannot be measured through the installed API. The
checkpoint therefore fails JOI's interactive TTS acceptance gate. It may remain
useful for non-interactive or queued speech, but it must not be integrated as
the primary conversational voice.

Run the suite from the isolated environment with cached weights:

```powershell
D:\JOI\.venv-tts\Scripts\python.exe .\qwen_tts_acceptance.py
```

## Kokoro TTS Evaluation

The full-precision Kokoro v1.0 ONNX model was evaluated on 2026-08-28 in an
isolated Python 3.13 environment using ONNX Runtime's CPU execution provider.
The model and voice files were downloaded explicitly from the official
`kokoro-onnx` v1.1 model-file release.

- Model load: 1.516 seconds
- Peak process RSS: 0.637 GiB
- Cold English RTF: 0.406
- Warm English RTF: 0.292
- Spanish RTF: 0.382
- Punctuation RTF: 0.222
- Long-text RTF: 0.259
- Streamed first audio: 1.505 seconds
- Stability soak: 20 of 20 generations, mean RTF 0.301
- Artifacts: 26 nonempty mono 24 kHz PCM-16 WAV files

Compared with Qwen3-TTS on this host, Kokoro's soak RTF is about 17 times lower
and its peak process RSS is about seven times lower. Kokoro passes JOI's
technical interactive-performance gate. Human listening approved `af_heart`
for English and accepted it temporarily for Spanish. The Spanish output has a
noticeable non-native accent, so the Spanish voice remains provisional and
should be replaced when a better local female voice is validated.

Local artifact hashes:

- `kokoro-v1.0.onnx`: `BEB0D1848DEE9A49DA392CC3DF26958D46CFA35D321EDF434F52949153F0DF3A`
- `voices-v1.0.bin`: `BCA610B8308E8D99F32E6FE4197E7EC01679264EFED0CAC9140FE9C29F1FBF7D`

Run the benchmark from the isolated environment:

```powershell
D:\JOI\.venv-kokoro\Scripts\python.exe .\kokoro_tts_benchmark.py
```

## Sources

- https://github.com/QwenLM/Qwen3-TTS
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
- https://huggingface.co/hexgrad/Kokoro-82M
- https://github.com/thewh1teagle/kokoro-onnx
- https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1
- https://github.com/QwenLM/Qwen3-ASR
- https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf