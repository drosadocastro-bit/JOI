# Compact Memory Post-FAIL Diagnostics

**Non-promotional diagnostic evidence. The Phase 5A gate remains open.**

- Generated: 2026-08-31T16:47:13.597531+00:00
- Corpus: `compact-memory-deterministic-v1`
- Frozen acceptance contract changed: no
- Live prompt injection: disabled
- Candidate publication: disabled
- Human review: incomplete

| Model | Updates | Timeout | Result | Failure | TTFT | First content | Total | Output tokens | tok/s | Prompt bytes | Min free RAM |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `nvidia/nemotron-3-nano` | 25 | 30s | rejected | model_timeout | 9.451s | n/a | 30.010s | None | n/a | 7058 | 2242875392 |
| `nvidia/nemotron-3-nano` | 50 | 30s | rejected | model_timeout | 4.013s | n/a | 30.011s | None | n/a | 9222 | 5060558848 |
| `nvidia/nemotron-3-nano` | 100 | 30s | rejected | model_timeout | 3.995s | n/a | 30.013s | None | n/a | 9196 | 4683169792 |
| `nvidia/nemotron-3-nano` | 200 | 30s | rejected | model_timeout | 3.579s | n/a | 30.006s | None | n/a | 8956 | 4384096256 |

## Interpretation Boundary

TTFT separates prefill or reasoning delay from visible structured-output delay only when the server emits reasoning events. Token counts are recorded only when LM Studio returns usage. Resource counters are observational and do not establish causality.

The frozen benchmark recommendation remains FAIL. These results cannot promote Compact Memory.
