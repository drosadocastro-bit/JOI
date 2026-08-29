# Local Brain Model Selection

Decision date: 2026-08-28

## Decision

Retain `nvidia/nemotron-3-nano` as JOI's default local conversational
model. Keep `qwen/qwen3.5-9b@q4_k_m` installed only as an experimental
secondary model for future guarded tool and vision work.

Qwen must not replace Nemotron until a supported non-thinking configuration
produces final text reliably and a repeat benchmark meets JOI's interactive
latency and exact-output gates.

## Host And Runtime

- Operating system: Windows
- CPU: AMD Ryzen 7 7735HS, 8 cores and 16 logical processors
- System RAM: 31.2 GiB
- Dedicated GPU: AMD Radeon RX 7700S, approximately 4 GiB dedicated VRAM
- Runtime: LM Studio local server using the Vulkan llama.cpp runtime
- Endpoint: `http://127.0.0.1:1234/v1`

The Windows adapter value is the dedicated allocation reported by WMI. Shared
system memory may be available to the GPU, but it is not equivalent to dedicated
VRAM and is not counted as such.

## Candidates

### Selected default

- Model: `nvidia/nemotron-3-nano@q4_k_m`
- Architecture: 30B mixture of experts, approximately 3.5B active parameters
- Local artifact size: 24.52 GB
- Role: responsive text conversation

### Evaluated candidate

- Model: `qwen/qwen3.5-9b@q4_k_m`
- Architecture: dense 9B vision-language model
- Local artifact size: 6.55 GB
- Advertised capabilities: reasoning, vision, multilingual conversation, and
  tool calling
- Benchmark context: 8,192 tokens
- Speculative decoding: disabled
- GPU offload: LM Studio automatic selection

## Controlled Benchmark

JOI's unchanged `phase1_acceptance.py` harness was run against both models. The
Qwen run used a process-only `LOCAL_MODEL=qwen/qwen3.5-9b` override; `.env` was
not changed. Each run used 20 sequential turns, exact-output instructions,
bounded session memory, and final recall of a marker introduced on turn 1.

| Metric | Nemotron 3 Nano | Qwen3.5-9B |
| --- | ---: | ---: |
| Exact responses | 20/20 | 19/20 |
| Minimum latency | 2.815 s | 3.912 s |
| Median latency | 4.239 s | 12.571 s |
| P95 latency | 6.853 s | 56.110 s |
| Maximum latency | 9.765 s | 72.344 s |
| Total latency | 97.235 s | 409.651 s |
| Final marker recall | Pass | Pass |

Qwen returned `TURN 10 OK` when `TURN 9 OK` was required. Its median latency
was approximately 3 times Nemotron's, and its P95 latency was approximately 8
times Nemotron's.

## Additional Qwen Observations

- Model load completed in 12.09 seconds and LM Studio reported 6.10 GiB for the
  8K configuration.
- Free system RAM fell from 15.13 GiB before load to 4.51 GiB after the soak.
- Two short English and Spanish probes each consumed the 256-token limit in
  reasoning content and returned no final `content` for speech.
- Attempts to disable thinking through the OpenAI-compatible endpoint were not
  honored by the installed LM Studio runtime.
- A mocked `get_current_time({})` request produced a correctly parsed tool call
  with `finish_reason=tool_calls` in 4.32 seconds. No tool was executed.
- Unloading Qwen restored free system RAM to 17.43 GiB.

## Interpretation

The Qwen artifact fits in memory, but memory fit does not establish suitability
for an interactive voice assistant. Empty final responses and long-tail latency
would make JOI appear unresponsive and can break the current text-to-speech
path. Tool-call parsing is promising, but all future tools must remain explicitly
allowlisted, validated, audited, and subject to human approval.

Official benchmark claims and advertised model capabilities were not treated as
local acceptance evidence. Only measurements produced through JOI's installed
runtime informed this decision.

## Reconsideration Gate

Re-evaluate Qwen only after all of the following are true:

1. LM Studio exposes and honors a verified non-thinking control for this model.
2. JOI handles reasoning fields without treating empty final content as success.
3. The 20-turn acceptance test completes with 20 exact responses.
4. Median and P95 latency satisfy an agreed interactive voice budget.
5. English, Spanish, vision, and adversarial tool-call tests pass locally.

## Sources

- https://huggingface.co/Qwen/Qwen3.5-9B
- https://lmstudio.ai/models/qwen3.5
- https://lmstudio.ai/docs/developer/openai-compat/chat-completions
