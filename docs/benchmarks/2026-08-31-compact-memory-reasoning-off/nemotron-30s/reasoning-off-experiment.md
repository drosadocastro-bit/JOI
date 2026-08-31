# Compact Memory Reasoning-OFF Shadow Experiment

**Primary budget: 30 seconds. Non-publishing. Phase 5A remains open.**

- Model: `nvidia/nemotron-3-nano`
- Corpus: `compact-memory-deterministic-v1`
- Reasoning control verified: True
- Outcome: **mixed cause**
- Frozen benchmark contract changed: no
- Durable Compact Memory modified: no
- Human review complete: no

| Updates | ON TTFT | ON first JSON | OFF TTFT | OFF first JSON | Total | Tokens in/out | Parse | Malformed | Accepted |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| 25 | 9.451 | n/a | 4.712 | 4.712 | 14.651 | 2006/135 | False | True | False |
| 50 | 4.013 | n/a | 19.061 | 19.061 | 30.004 | None/None | False | False | False |
| 100 | 3.995 | n/a | 19.333 | 19.333 | 29.735 | 2664/139 | False | True | False |
| 200 | 3.579 | n/a | 21.050 | 21.050 | 21.628 | 2699/9 | False | True | False |

> Default-on reasoning is consuming the latency budget before Compact Memory can emit structured claims.

All reasoning-OFF checkpoints failed. Stop model tuning and reconsider the summarizer architecture or provider.
