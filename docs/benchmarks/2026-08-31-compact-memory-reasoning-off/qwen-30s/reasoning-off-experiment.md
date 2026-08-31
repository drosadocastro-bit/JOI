# Compact Memory Reasoning-OFF Shadow Experiment

**Primary budget: 30 seconds. Non-publishing. Phase 5A remains open.**

- Model: `qwen/qwen3.5-9b`
- Corpus: `compact-memory-deterministic-v1`
- Reasoning control verified: True
- Outcome: **model suitability failure**
- Frozen benchmark contract changed: no
- Durable Compact Memory modified: no
- Human review complete: no

| Updates | ON TTFT | ON first JSON | OFF TTFT | OFF first JSON | Total | Tokens in/out | Parse | Malformed | Accepted |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| 25 | n/a | n/a | n/a | n/a | 30.008 | None/None | False | False | False |
| 50 | n/a | n/a | n/a | n/a | 30.012 | None/None | False | False | False |
| 100 | n/a | n/a | n/a | n/a | 30.009 | None/None | False | False | False |
| 200 | n/a | n/a | n/a | n/a | 30.004 | None/None | False | False | False |

> Default-on reasoning is consuming the latency budget before Compact Memory can emit structured claims.

All reasoning-OFF checkpoints failed. Stop model tuning and reconsider the summarizer architecture or provider.
