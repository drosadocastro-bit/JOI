# Compact Memory Post-FAIL Diagnostics

**Non-promotional diagnostic evidence. The Phase 5A gate remains open.**

- Generated: 2026-08-31T16:50:37.453818+00:00
- Corpus: `compact-memory-deterministic-v1`
- Frozen acceptance contract changed: no
- Live prompt injection: disabled
- Candidate publication: disabled
- Human review: incomplete

| Model | Updates | Timeout | Result | Failure | TTFT | First content | Total | Output tokens | tok/s | Prompt bytes | Min free RAM |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen/qwen3.5-9b` | 25 | 30s | rejected | model_timeout | n/a | n/a | 30.003s | None | n/a | 7051 | 4395454464 |
| `qwen/qwen3.5-9b` | 50 | 30s | rejected | model_timeout | n/a | n/a | 30.007s | None | n/a | 9215 | 12199636992 |
| `qwen/qwen3.5-9b` | 100 | 30s | rejected | model_timeout | n/a | n/a | 30.001s | None | n/a | 9189 | 11915329536 |
| `qwen/qwen3.5-9b` | 200 | 30s | rejected | model_timeout | n/a | n/a | 30.014s | None | n/a | 8949 | 11724283904 |

## Interpretation Boundary

TTFT separates prefill or reasoning delay from visible structured-output delay only when the server emits reasoning events. Token counts are recorded only when LM Studio returns usage. Resource counters are observational and do not establish causality.

The frozen benchmark recommendation remains FAIL. These results cannot promote Compact Memory.
