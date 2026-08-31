# Compact Memory Real-Model Benchmark

**Recommendation: FAIL**

- Generated: 2026-08-31T16:16:36.642324+00:00
- Environment: Windows-11-10.0.26200-SP0
- Python: 3.13.7
- Model: `nvidia/nemotron-3-nano`
- Endpoint: `http://127.0.0.1:1234/v1`
- Parameters: LM Studio API defaults; stream=false
- Request timeout: 30 seconds
- Corpus: `joi-compact-memory-deterministic@compact-memory-deterministic-v1`
- Completed updates: 200
- Execution: independent cumulative checkpoint snapshots
- Trials per checkpoint: 1
- Maximum source characters: 2000
- Live prompt injection: disabled
- Human review: incomplete

## Checkpoints

| Updates | Extractive | Model | Coverage | Unsupported | Provenance | Correction | Forgetting | Compression | Bytes | Avg latency | P95 latency | Failures |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 25 | 49 | 0 | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 30.003s | 30.003s | 1 |
| 50 | 65 | 0 | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 30.013s | 30.013s | 1 |
| 100 | 65 | 0 | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 30.012s | 30.012s | 1 |
| 200 | 62 | 0 | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 30.004s | 30.004s | 1 |

Average and P95 latency are identical because this run used one real-model trial per cumulative checkpoint.

## Extractive Vs Model

At the final checkpoint, the extractive baseline retained 62 claims while the model-backed candidate retained 0. Model factual coverage was 0.000.

## Failures

- Candidate failures: 4
- Hard failures: 0

Phase 5A remains shadow-only until human review is complete.
