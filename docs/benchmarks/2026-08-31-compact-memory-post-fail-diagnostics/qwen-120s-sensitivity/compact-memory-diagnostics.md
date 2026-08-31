# Compact Memory Post-FAIL Diagnostics

**Non-promotional diagnostic evidence. The Phase 5A gate remains open.**

- Generated: 2026-08-31T16:53:54.722950+00:00
- Corpus: `compact-memory-deterministic-v1`
- Frozen acceptance contract changed: no
- Live prompt injection: disabled
- Candidate publication: disabled
- Human review: incomplete

| Model | Updates | Timeout | Result | Failure | TTFT | First content | Total | Output tokens | tok/s | Prompt bytes | Min free RAM |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen/qwen3.5-9b` | 25 | 120s | rejected | model_timeout | 12.629s | n/a | 120.015s | None | n/a | 7051 | 2954203136 |

## Interpretation Boundary

TTFT separates prefill or reasoning delay from visible structured-output delay only when the server emits reasoning events. Token counts are recorded only when LM Studio returns usage. Resource counters are observational and do not establish causality.

The frozen benchmark recommendation remains FAIL. These results cannot promote Compact Memory.
