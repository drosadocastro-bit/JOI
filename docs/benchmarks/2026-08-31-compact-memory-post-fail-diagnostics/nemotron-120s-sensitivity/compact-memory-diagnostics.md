# Compact Memory Post-FAIL Diagnostics

**Non-promotional diagnostic evidence. The Phase 5A gate remains open.**

- Generated: 2026-08-31T16:58:00.678013+00:00
- Corpus: `compact-memory-deterministic-v1`
- Frozen acceptance contract changed: no
- Live prompt injection: disabled
- Candidate publication: disabled
- Human review: incomplete

| Model | Updates | Timeout | Result | Failure | TTFT | First content | Total | Output tokens | tok/s | Prompt bytes | Min free RAM |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `nvidia/nemotron-3-nano` | 25 | 120s | rejected | model_timeout | 31.315s | n/a | 120.013s | None | n/a | 7058 | 409600 |

## Interpretation Boundary

TTFT separates prefill or reasoning delay from visible structured-output delay only when the server emits reasoning events. Token counts are recorded only when LM Studio returns usage. Resource counters are observational and do not establish causality.

The frozen benchmark recommendation remains FAIL. These results cannot promote Compact Memory.
