# Phase 5A: Compact Memory Closure Gate

## Status And Scope

This document defines the acceptance gate for moving Compact Memory from the
implemented extractive shadow baseline to a validated model-backed shadow
system. The disabled model-backed path, structured validation, policy-aware
regeneration, paired reporting, and deterministic drift regression are now
implemented. The gate is not approved until real-model and human-review
evidence satisfies the acceptance criteria below.

The goal is to evaluate whether a local model can improve compression without
introducing memory drift, unsupported claims, or leakage from corrected or
logically forgotten evidence. Compact Memory remains derived, local,
inspectable, and absent from live prompts throughout this phase.

The first real-model run on 2026-08-31 received a **FAIL** recommendation.
`nvidia/nemotron-3-nano` timed out at the 30-second benchmark limit for each
independent cumulative checkpoint at 25, 50, 100, and 200 updates. No candidate
claim passed validation or became durable. The extractive baseline remained
available, no hard safety invariant was violated, and live prompt injection
remained disabled. Results are recorded in
[the benchmark report](benchmarks/2026-08-31-nemotron-compact-memory-checkpoints/compact-memory-benchmark.md).

## 5A.1 Preserve The Extractive Baseline

Keep `extractive-v1` as the control implementation.

Requirements:

- Do not remove or weaken the extractive summarizer.
- Record baseline output from the same effective source turns supplied to the
  model-backed candidate.
- Preserve source turn IDs, summary version, generation timestamp, and
  summarizer identifier.
- Isolate baseline failures from conversation and episodic storage.

The extractive implementation remains the fidelity and drift reference.

## 5A.2 Add A Model-Backed Shadow Candidate

Add a second Compact Memory path backed only by the configured local LLM:

```text
completed exchanges
  -> effective source view
       +-> extractive baseline
       +-> model-backed candidate
```

Requirements:

- `ENABLE_MODEL_COMPACT_MEMORY=false` by default.
- Enabling it requires persistent memory and Compact Memory.
- Model output never enters the live prompt during this phase.
- A model candidate cannot replace the approved extractive baseline until this
  document's acceptance gate passes.
- Model timeout, unavailability, or failure cannot affect conversation,
  episodic persistence, or the last valid Compact Memory state.
- No network fallback is permitted.

## 5A.3 Enforce Structured Output

Do not persist free-form model prose as Compact Memory. Validate a versioned
structure before any candidate write:

```json
{
  "summary_version": 1,
  "generated_at_utc": "2026-08-31T12:00:00+00:00",
  "summarizer": "model-v1:nvidia/nemotron-3-nano",
  "source_policy_revision": 42,
  "claims": [
    {
      "claim_id": "claim-101",
      "text": "The user prefers concise technical explanations.",
      "source_turn_ids": ["turn-101", "turn-104"],
      "source_policy_ids": [null, "policy-22"],
      "confidence": 0.92,
      "status": "explicit",
      "generated_at_utc": "2026-08-31T12:00:00+00:00",
      "summarizer": "model-v1:nvidia/nemotron-3-nano"
    }
  ]
}
```

Required state fields:

- summary version
- generation timestamp in UTC
- summarizer and model identifier
- source policy revision
- claims array

Required claim fields:

- stable claim ID
- claim text
- source turn IDs
- corresponding effective source policy IDs, including `null` for an
  unmodified source
- confidence in the inclusive range 0 through 1
- `explicit` or `inferred` classification
- generation timestamp in UTC
- summarizer and model identifier

Reject unknown schema versions, malformed JSON, duplicate claim IDs, missing
fields, invalid values, and empty provenance. Model-reported confidence is
diagnostic metadata, not evidence of truth and not sufficient for acceptance.

## 5A.4 Prevent Recursive Drift

Never use summary prose as independent source evidence. Preferred update input:

```text
previous valid compact state as a retention proposal
+ bounded new completed exchanges
+ current effective correction and forgetting state
  -> candidate compact state
```

The previous state may propose claims for retention, but every retained claim
must be revalidated against current effective raw evidence. A claim without
surviving provenance is rejected. Full regeneration from episodic evidence
must remain possible and produce an auditable comparison result.

Do not introduce summary-of-summaries in this phase.

## 5A.5 Validate Provenance

Before accepting a candidate claim, verify that:

- every source turn exists
- every source belongs to a valid completed user/assistant exchange
- no source is logically forgotten
- each source policy ID matches the current effective correction state
- corrected content, rather than superseded raw content, is used for support
- the state-level policy revision still matches at atomic write time

Reject the complete candidate when any provenance check fails.

> No Compact Memory claim survives without reconstructable current source
> evidence.

## 5A.6 Reject Unsupported And Inferred Claims

Validate claim text against the effective source content. Initial policy:

- reject unsupported factual claims
- exclude inferred claims from accepted Compact Memory
- retain inferred output only in ephemeral evaluation reports
- reserve associations and inference for later graph or dreaming layers

Track:

- unsupported claim count and rate
- inferred and explicit claim counts
- validator disagreements
- rejected candidate count and reason

Unsupported-claim detection must not rely on the generating model's confidence
alone. The initial validator should combine deterministic source constraints
with a separately recorded support judgment. Any uncertain judgment rejects
the claim. If one claim fails, reject the complete candidate so no partial
state is published.

## 5A.7 Regenerate After Correction

When `/memory correct` supersedes a source used by Compact Memory:

```text
correction policy appended
  -> dependent current claims become stale
  -> regenerate from the current effective source view
  -> validate the complete candidate
  -> atomically publish or preserve the previous valid state
```

Never patch summary prose directly. Preserve old candidate artifacts and
evaluation reports as historical audit records, while only the validated
candidate at the current policy revision may be considered current.

## 5A.8 Enforce Logical Forgetting

When `/memory forget` suppresses a source:

- immediately mark dependent current claims stale
- stop surfacing those claims in current Compact Memory inspection
- exclude forgotten evidence from every later summarization input
- invalidate or regenerate every dependent claim
- retain immutable raw evidence under the episodic-store policy

Required test:

```text
claim exists
  -> /memory forget
  -> summary regeneration
  -> forgotten claim does not return
```

This behavior must also survive process restart.

## 5A.9 Publish Atomically

Candidate validation and publication must behave transactionally. Reject the
candidate and preserve the last valid state on:

- timeout or summarizer unavailability
- malformed or invalid structured output
- missing or invalid provenance
- unsupported or inferred claims
- correction conflict or policy-revision race
- forgotten source
- storage failure

No partial claim set may be written. Conversation and raw episodic persistence
continue without hidden retries.

## 5A.10 Build An Evaluation Harness

Run the extractive baseline and model-backed candidate over identical effective
histories. Emit versioned machine-readable JSON reports containing:

- corpus and run identifiers
- exact summarizer and model identifiers
- generation settings
- factual coverage
- unsupported-claim and contradiction rates
- provenance coverage
- compression ratio
- stale-claim rate
- correction and forgetting adherence
- latency and token counts
- serialized storage growth
- candidate rejection reasons

Evaluation must be reproducible from the corpus, raw episodic evidence, policy
records, configuration, and recorded model identifier.

## 5A.11 Measure Drift

Evaluate fresh stores at 25, 50, 100, and 200 updates. At each checkpoint
measure:

- factual retention and important-claim loss
- false additions and contradictions
- correction survival
- forgotten-memory resurrection
- summary size and compression ratio
- provenance integrity
- regeneration consistency

Do not add another compression layer in response to observed drift during this
phase. Record the failure and diagnose the current layer first.

## 5A.12 Maintain A Human Review Corpus

Create a small, local, synthetic or explicitly approved corpus containing:

- explicit and changed preferences
- corrections and forgotten memories
- bilingual English and Spanish turns
- ambiguous and repeated statements
- contradictory facts
- technical project context
- casual relational context

For each case, define expected retained, rejected, corrected, and forgotten
claims. Do not place private production conversations in the tracked corpus.

## 5A.13 Test Failure And Corruption

Add pytest-discoverable coverage for:

- model timeout and unavailable summarizer
- invalid JSON and missing `claims`
- missing or nonexistent source turn IDs
- logically forgotten and superseded sources
- duplicate claim IDs
- corrupted previous Compact Memory state
- storage write failure
- policy revision changing during generation
- restart after correction or forgetting

> Compact Memory failure may reduce memory quality; it must not reduce
> conversation availability.

## 5A.14 Report Shadow Comparisons

Provide developer-visible, non-prompt reporting for:

- baseline and candidate claim counts
- shared, candidate-only, and baseline-only claims
- unsupported claims and provenance failures
- stale and invalidated claims
- latency and compression ratio
- candidate acceptance or rejection reason

Reports must redact configured secrets and must not introduce telemetry or an
implicit network dependency.

## Acceptance Gate

Phase 5A closes only when all of the following are demonstrated:

- the extractive baseline remains available
- the local model summarizer runs reliably in shadow mode
- structured output validation rejects malformed candidates
- accepted claims have 100% valid, current source provenance
- accepted Compact Memory has zero known unsupported or inferred claims in the
  evaluation corpus
- correction and forgetting adherence are 100%, including after restart
- failed updates preserve the previous valid state and conversation operation
- drift is measured at 25, 50, 100, and 200 updates
- the human review corpus passes its agreed expectations
- corruption and failure tests pass
- model-backed factual coverage matches or exceeds the extractive baseline
- an explicit latency and storage budget is recorded before approval
- model-backed Compact Memory remains shadow-only until a separate retrieval
  gate is approved

These are minimum safety criteria, not automatic approval. Any unresolved
contradiction, forgotten-memory resurrection, or provenance failure blocks the
gate. Performance thresholds that depend on benchmark measurements must be
recorded before promotion rather than selected after observing results.

## Explicit Non-Goals

Do not add in Phase 5A:

- NIC graph or vector retrieval
- relational inference
- dream consolidation
- summary-of-summaries
- autonomous pruning
- live memory prompt injection
- learned policy adaptation

These remain blocked until Compact Memory passes this gate.

## Design Invariants

1. Raw evidence remains immutable.
2. Compact Memory is derived state, not authority.
3. A prettier summary is not necessarily a better summary.
4. Unsupported claims are worse than incomplete summaries.
5. Corrections outrank old derived claims.
6. Logical forgetting propagates into derived state.
7. Every durable claim has current, reconstructable provenance.
8. Failed summarization never breaks live conversation.
9. Model-backed summarization remains shadow-only until validated.
10. No later memory layer hides Compact Memory defects.

## Guiding Principle

> Slightly boring but faithful beats wonderfully human but fabricated.