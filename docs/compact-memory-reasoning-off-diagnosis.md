# Compact Memory Reasoning-OFF Diagnosis

**Outcome: mixed cause. Stop model tuning and reconsider the summarizer architecture or provider.**

This shadow experiment freezes `f9d8375` as reasoning-ON evidence. It uses the
same deterministic corpus, 25/50/100/200 checkpoints, 2,000-character source
bound, model prompt, parser, provenance validator, and primary 30-second budget.
The only generation-control change is `reasoning_effort: "none"` on the same LM
Studio chat-completions endpoint.

Reasoning-OFF was verified independently for each loaded model with a one-token
control response reporting zero reasoning tokens. Candidate publication was not
available in the experiment code. Durable Compact Memory was not modified, and
the previous valid memory remains authoritative.

## Direct Comparison

| Model | Updates | ON first token | ON first JSON | OFF first token | OFF first JSON | OFF total | Tokens in/out | Parse | Malformed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| Nemotron | 25 | 9.451s | none | 4.712s | 4.712s | 14.651s | 2006/135 | fail | yes |
| Nemotron | 50 | 4.013s | none | 19.061s | 19.061s | 30.004s | unavailable | fail | incomplete timeout |
| Nemotron | 100 | 3.995s | none | 19.333s | 19.333s | 29.735s | 2664/139 | fail | yes |
| Nemotron | 200 | 3.579s | none | 21.050s | 21.050s | 21.628s | 2699/9 | fail | yes |
| Qwen3.5-9B | 25 | none | none | none | none | 30.008s | unavailable | fail | no output |
| Qwen3.5-9B | 50 | none | none | none | none | 30.012s | unavailable | fail | no output |
| Qwen3.5-9B | 100 | none | none | none | none | 30.009s | unavailable | fail | no output |
| Qwen3.5-9B | 200 | none | none | none | none | 30.004s | unavailable | fail | no output |

Token counts are `null` when LM Studio timed out before returning usage. Raw
rejected Nemotron output is preserved in the per-model JSON artifacts. Qwen
produced no output to preserve.

## Classification

**Nemotron: mixed cause.** Disabling reasoning moved JSON content inside the
budget at every checkpoint, strongly supporting reasoning-budget starvation in
the ON configuration. However, no output matched the frozen candidate schema:
required top-level metadata and claim text were missing, confidence types were
invalid, or the response was incomplete. This is also structured-output
incompatibility. Its 24.52 GB footprint on a 31.2 GiB host remains a material
resource-pressure risk; earlier ON sensitivity evidence reached effectively zero
free RAM.

**Qwen3.5-9B: model suitability failure.** Its OFF control completed in 0.657s
with zero reasoning tokens, proving the control and endpoint worked. The full
Compact Memory request emitted no token at any checkpoint within 30 seconds,
despite approximately 9.5-11.0 GiB minimum free RAM. Reasoning-OFF did not recover
the task.

**Overall: mixed cause.** The central hypothesis is supported but incomplete:

> **Default-on reasoning is consuming the latency budget before Compact Memory can emit structured claims.**

That explains Nemotron's ON-to-OFF transition to prompt JSON emission. It does
not explain malformed candidates or Qwen's full-task failure.

No candidate passed parsing and provenance validation, so factual coverage,
provenance coverage, correction adherence, forgetting adherence, and compression
are unavailable. Assigning values would be misleading.

Both models failed reasoning-OFF. Per the experiment stop rule, do not continue
model tuning or reinterpret longer runs as promotional evidence. Reconsider a
smaller deterministic extraction architecture, constrained-decoding provider, or
non-generative claim-selection stage before another model benchmark.

Phase 5A remains open until the human-review corpus and every closure-gate
criterion pass.

## Evidence

- `docs/benchmarks/2026-08-31-compact-memory-reasoning-off/nemotron-30s`
- `docs/benchmarks/2026-08-31-compact-memory-reasoning-off/qwen-30s`
- `docs/benchmarks/2026-08-31-compact-memory-reasoning-off/reasoning-on-off-comparison.json`

Each per-model artifact embeds SHA-256 hashes for all eight frozen `f9d8375`
diagnostic files.