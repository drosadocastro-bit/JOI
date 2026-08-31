# Compact Memory Post-FAIL Diagnosis

**Status: diagnosed, unresolved, shadow-only**

This investigation preserves the benchmark and acceptance contract committed at
`dedf2b8`. It does not change the frozen corpus, 25/50/100/200 checkpoints,
2,000-character source bound, claim schema, validation rules, 30-second budget,
or FAIL recommendation. Candidate publication and live prompt injection remained
disabled.

## Evidence

The streaming diagnostic runner reused the production `ModelCompactSummarizer`
prompt and validators. It recorded total history size separately from the bounded
request, first reasoning/content timing, LM Studio usage when returned, parse and
validation outcomes, and local resource samples. Every artifact embeds SHA-256
hashes for the frozen benchmark evidence.

| Model | Checkpoints | Prompt bytes | 30s TTFT | First JSON content | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Nemotron 3 Nano Q4_K_M | 25/50/100/200 | 7,058-9,222 | 3.58-9.45s | none | four timeouts |
| Qwen3.5 9B Q4_K_M | 25/50/100/200 | 7,051-9,215 | none | none | four timeouts |

At 120 seconds on checkpoint 25:

- Nemotron emitted its first reasoning token at 31.31 seconds and 1,097 reasoning
  events, but no JSON content.
- Qwen emitted its first reasoning token at 12.63 seconds and 1,792 reasoning
  events, but no JSON content.
- Neither model returned final usage fields because neither response completed.

Nemotron's active LM Studio configuration used a 1,048,576-token context,
parallelism 4, default-on reasoning, no speculative decoding, and a 24.52 GB model
on a host with 31.2 GiB RAM and about 4 GiB dedicated VRAM. Its 120-second trial
reduced measured available system RAM to less than 1 MiB. Qwen loaded at 6.55 GB
with a 262,144-token context and default-on reasoning. Its minimal two-message JSON
control also emitted no event within 30 seconds, so its strict-timeout result is
not specific to the Compact Memory prompt.

## Diagnosis

The evidence does **not** support raw Compact Memory task size as the primary
cause. After checkpoint 50, the bounded prompts remained approximately the same
size, while Nemotron TTFT improved after warmup and all checkpoints still failed
in the same way.

The direct blocking behavior is prolonged structured generation behind
default-on reasoning. Both models generated reasoning without reaching JSON even
at 120 seconds. This establishes where the latency budget is consumed; it does
not establish that reasoning is the only cause.

Nemotron is unsuitable for the current 30-second summarizer budget and host under
the measured configuration. Severe RAM pressure is a material confounder and a
separate operational reason not to select it. Qwen is materially smaller but is
also unsuitable under its measured default-on reasoning configuration. No model
is approved by this diagnosis.

## Required Next Experiment

Run a separate, versioned comparison with reasoning explicitly disabled where LM
Studio supports that request control. Keep the frozen corpus, schema, provenance
validation, and 30-second budget unchanged. Record the exact API field and active
load configuration. This is a new configuration experiment, not a reinterpretation
of the frozen benchmark or the evidence here.

Phase 5A remains open. Human review, full factual coverage, correction and
forgetting adherence, and every existing acceptance criterion remain mandatory.

## Artifacts

- `docs/benchmarks/2026-08-31-compact-memory-post-fail-diagnostics/nemotron-30s`
- `docs/benchmarks/2026-08-31-compact-memory-post-fail-diagnostics/nemotron-120s-sensitivity`
- `docs/benchmarks/2026-08-31-compact-memory-post-fail-diagnostics/qwen-30s`
- `docs/benchmarks/2026-08-31-compact-memory-post-fail-diagnostics/qwen-120s-sensitivity`

The 120-second sensitivity results are non-promotional and cannot redefine
the 30-second acceptance budget.