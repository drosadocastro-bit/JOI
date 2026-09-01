# Phase 5A Closure Audit

## Decision

**Phase 5A closure decision: PASS with known limitations.**

This decision closes the provider-contract and retention-quality evaluation
scope. It does not authorize publication, live prompt injection, retrieval, or
production dependence on model-backed Compact Memory. Those remain separate
human decisions.

Audit time: `2026-09-01T15:44:31.5056970Z`

## Baseline And Evidence Pin

- Frozen source baseline: commit `8f004a7` on `main`.
- Commit role: last committed local-model diagnosis baseline and source baseline
  used by the cloud benchmark.
- Phase 5A closure commit: `6628591a0e5d12fb1502f0350c8a5dbd960b2532`.
- Worktree at audit start: dirty, containing the provider, benchmark, review,
  tests, and closure changes.
- Post-closure-commit worktree: clean before the administrative SHA pin update.
- Committed regression: 174 tests passed.

Primary evidence indexes and diagnoses are pinned below. The manifests contain
the hashes of every subordinate frozen artifact.

| Evidence | SHA-256 |
| --- | --- |
| `docs/compact-memory-post-fail-diagnosis.md` | `478316ac7e6fa5cdab6892e873d62448f1a16d0d6e2e573ad33003ab34345f0c` |
| `docs/compact-memory-reasoning-off-diagnosis.md` | `b3d9b7235326fe7ef377c00e4302e3f705cce342a230a7989c7b249a9c06cd7c` |
| `docs/benchmarks/2026-08-31-openai-compact-memory/manifest.json` | `a85064904f067d9ad2f390e8774ec287fe31e3517b7c3d00aed464ee3125b096` |
| `docs/benchmarks/2026-08-31-openai-compact-memory/full/baseline-freeze.json` | `a5e97b0c182472fe5aeb389aa9eaf01dabfa7e17ad6a56290b2a90c6e12a4af3` |
| `docs/benchmarks/2026-09-01-retention-quality/execution-manifest.json` | `cdd2b8d4bcfb52de2ec7e64bca77ca59df8edeb49473894f97f75f5f57d40cde` |
| `docs/benchmarks/2026-09-01-retention-quality/final-review-manifest.json` | `10a8a01588c8956317871787cbd983207d11d66a189a3e52bc549b61091b0412` |

### Cloud Full-Benchmark Artifacts

| Artifact | SHA-256 | Bytes |
| --- | --- | ---: |
| `cloud-benchmark.json` | `78ebbaf293c1717e5e954e0a8b0b84b34f133f33350bbe8993b4b572851689bc` | 4,223 |
| `cloud-benchmark.md` | `f5abafb88680a0196d3d52c0dd3bd008de38e71d7516931110dbefcf0f370a4b` | 787 |
| `model-candidate.json` | `e1c6406cc659914d0b80215770a1021c3a23e77ba0fd09675f66c350bd431843` | 11,330 |
| `update-reports.json` | `a29236123d932af656355deefdf2029f5314ec463b5f4ba5ec895886b855d5cb` | 95,118 |

### Retention-Quality Artifacts

| Artifact | SHA-256 | Bytes |
| --- | --- | ---: |
| `preregistration.json` | `42af88fd0e803fe1b075382263c7b83e2ce26720eb34257f01b187b406902a1a` | 3,148 |
| `reference-labels.json` | `0ac9208028a5fab4d65a68ce7dbb8b128a03f8f8414f0025f91d189ea74cebdb` | 10,632 |
| `luna/model-candidate.json` | `0bfba1791d2c547bd7b00bc7f697e853cbae142dbbfdb6a9e81709168de5190e` | 7,883 |
| `luna/retention-quality-report.json` | `878d63c7fc61a4de62b4d8375b15f713d1dad23a756ec7ab3db597ad17220ccd` | 5,540 |
| `luna/retention-quality-report.md` | `938914d00483923ac1d4a486043bc5884f372bdd35f469ca7f31e27e4759595e` | 955 |
| `luna/human-review-template.json` | `8a834fccc0109101d1ad38a17c7980325edf6840d86f3108db1693f3f41ca0a0` | 1,789 |
| `luna/human-review.json` | `161773b2527bbe6146062f51c89f299dca6bed87e4087dc3b74e1fd32087121e` | 2,284 |
| `luna/retention-quality-final.json` | `7f0554fb6e133fd50b5af2be2d954d96be3eb79989b7da6ae8b318d9afb1d825` | 6,140 |
| `luna/retention-quality-final.md` | `d25e705d7b4f0105fd8d70f32b37bf3672026280fa09817ac6b8b77fc85d5b26` | 918 |

## Local Model Findings

The local evidence was generated on Windows 11, Python 3.13.7, an AMD64 Family
25 Model 68 host, 31.2 GiB system RAM, and approximately 4 GiB dedicated VRAM.
The corpus used independent cumulative checkpoints at 25, 50, 100, and 200
updates, a 2,000-character source bound, and one trial per checkpoint.

Nemotron 3 Nano Q4_K_M was a 24.52 GB model with a 1,048,576-token context,
parallelism 4, and default-on reasoning. It timed out at approximately 30 seconds
at all four checkpoints. At a non-promotional 120-second checkpoint-25 trial it
emitted reasoning at 31.31 seconds but no JSON; available RAM fell below 1 MiB.

Qwen3.5 9B Q4_K_M was a 6.55 GB model with a 262,144-token context and
default-on reasoning. It emitted no result within 30 seconds at any checkpoint.
At a non-promotional 120-second checkpoint-25 trial it emitted reasoning at
12.63 seconds but no JSON.

Reasoning OFF was independently verified with zero reasoning tokens. Nemotron
then emitted JSON content inside the budget at all checkpoints, but every output
was malformed, incomplete, or schema-incompatible and none passed parsing and
provenance validation. Qwen's control completed in 0.657 seconds, but the full
task still emitted no token within 30 seconds at any checkpoint. The diagnosis
is therefore mixed: reasoning-budget starvation contributed to Nemotron's
latency, structured-output incompatibility remained, and Qwen had a task-level
model-suitability failure. No local model was approved.

## Provider And Cloud-Gating Validation

JOI owns memory state, validation, and persistence. Providers only generate a
candidate and telemetry. Tests verify:

- provider health is checked before generation;
- an unhealthy provider is not executed;
- call-time CLOUD OFF refuses generation before opening a request;
- OpenAI Compact Memory configuration requires CLOUD opt-in and an API key;
- only the official OpenAI HTTPS endpoint is accepted;
- API keys are redacted from provider errors and benchmark artifacts;
- strict Responses API JSON Schema and reasoning effort `none` are sent;
- provider/model identity mismatch is rejected;
- providers have no JOI state or memory-store ownership;
- provider switching does not mutate JOI state or source memory; and
- provider failure preserves the previous manager state and performs no save.

## Luna Provider-Contract Result

`gpt-5.6-luna` passed all independent 25/50/100/200 checkpoints using the
OpenAI Responses API with strict structured output and reasoning effort `none`.
There were four accepted samples, no malformed candidates, no hard failures,
no unsupported factual claims, 100% provenance coverage, 100% correction
adherence, and 100% forgetting adherence. Checkpoint latency was 15.73, 17.15,
20.09, and 19.95 seconds. The full run used 9,274 input tokens and 10,368 output
tokens at an estimated cost of USD 0.0142964.

Raw factual coverage against the extractive claim count was 47.69% to 49.23%.
That metric did not meet the original literal baseline-coverage criterion and is
not represented as a pass. The later preregistered retention-quality benchmark
evaluated whether omitted information was semantically important.

## Retention Quality And Human Adjudication

The preregistered, balanced six-category corpus generated one frozen Luna
candidate without prompt or schema changes after results were opened. It
retained 20 of 24 facts: raw coverage 83.33%, weighted retention 100%, critical
retention 100%, zero forbidden losses, and zero provenance failures. A human
reviewer classified all four omitted generic acknowledgements as acceptable
compression, with zero harmful omissions, disagreements, or unreviewed items.
The final retention-quality decision is PASS.

## Closure Regression

The executable closure regression produced these results:

- complete pytest suite: PASS, 174 tests;
- JSON validation: PASS, 34 documents parsed as UTF-8;
- frozen hash verification: PASS, 19 manifest entries;
- credential-pattern scan: PASS, 124 tracked/non-ignored files plus 10 runtime
  log, memory, and snapshot artifacts, with zero non-test credential patterns;
- durable memory mutation check: PASS, before/after SHA-256
  `85f50c5faceab67e201f89fdf3dad1d714437bb1ed4d7e2a316db28616c12c7a`;
- `git diff --check`: PASS; and
- editor diagnostics for closure artifacts: PASS.

The broad workspace scan found a live-looking key in the ignored local `.env`.
It was not present in publishable files or benchmark artifacts, but inspection
exposed it to tooling. The human operator must revoke/rotate it immediately and
revalidate cloud access before any later provider run. On
`2026-09-01T16:16:09.1258009Z`, the human operator confirmed that the exposed
key was revoked and a replacement was created. JOI verified only that a
non-empty replacement is present in the ignored local `.env`; it did not print,
persist, hash, or use the replacement in a cloud request. The value is not
copied into this audit.

The substantive closure commit was clean immediately after creation. Its SHA is
pinned by a separate administrative follow-up because a commit cannot contain
its own SHA. The final worktree is checked again after that pin commit.

Credential lifecycle regression additionally verifies in-process revoke to
replace to reload behavior, missing-key refusal before network access,
simulated revoked-key rejection, stale-key non-reuse, no provider fallback,
redacted exceptions and logs, no candidate-memory mutation, and no secret in
persisted evaluation artifacts. The operator procedure is recorded in
`docs/openai-key-rotation-recovery.md`. `TD-JOI-008` remains open because these
deterministic tests do not exercise provider-side revocation, account policy,
or a production secret store end to end.

## What Phase 5A Proves

Under the recorded corpora, provider, model, prompts, schema, one-trial
checkpoints, hardware, endpoint, and dates, Phase 5A proves that:

- JOI can use a provider without transferring ownership of state or memory;
- cloud use is explicit, call-time gated, endpoint constrained, and redacted;
- malformed, unsupported, stale, forgotten, or invalid-provenance candidates
  are rejected before persistence;
- failed provider generation preserves the previous valid Compact Memory;
- Luna satisfied the 25/50/100/200 provider contract in the frozen run;
- Luna retained every weighted and protected fact in the frozen quality corpus;
- all observed omissions were human-adjudicated acceptable compression; and
- benchmark PASS, publication, and runtime authorization are separate states.

## What Phase 5A Does Not Prove

Phase 5A does not prove that:

- Nemotron or Qwen is suitable on other hardware or under other configurations;
- Luna or any provider will behave identically across repeated or future runs;
- raw factual coverage matches or exceeds the extractive baseline;
- the small synthetic human-review corpus represents production conversations;
- Compact Memory remains drift-free over long horizons;
- provider switches preserve semantic continuity over extended histories;
- live outages, rate limits, revoked keys, or partial corruption are fully
  recovered operationally;
- provenance is consistent across multiple cloud providers;
- schema migrations and rollback are durable; or
- model-backed Compact Memory is approved for publication, retrieval, live
  prompts, autonomous action, or safety-critical authority.

## Authorization Boundary

- Benchmark decision: `PASS`.
- Phase status: `CLOSED_WITH_KNOWN_LIMITATIONS`.
- Candidate publication: `false`.
- Live prompt injection: `false`.
- Retrieval authorization: not granted.
- Runtime CLOUD authorization: still required at call time.
- Promotion authority: human only; no benchmark changes this state implicitly.

## Next-Phase Entry Prerequisites

Before any phase enables publication, retrieval, or production reliance:

1. Review every globally `BLOCKING` debt against the exact proposed phase.
2. Resolve `TD-JOI-009` before Phase 5B shadow retrieval implementation.
3. Keep `TD-JOI-006`, `TD-JOI-007`, `TD-JOI-008`, and `TD-JOI-011` blocking
  for operational provider use, publication, or schema evolution.
4. Freeze the Phase 5B corpus, labels, numeric thresholds, dependencies, and
  final Phase 5A commit before executing the preregistered experiment.
5. Obtain a separate explicit human authorization record before publication,
  prompt injection, retrieval activation, or production reliance.

The next architecture/evaluation gate is preregistered in
`docs/phase-5b-shadow-retrieval-preregistration.md`. Creating that note does not
start Phase 5B implementation.

Passing evidence does not erase technical debt; it bounds the claims JOI may
make.