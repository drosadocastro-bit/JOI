# Phase 5B Shadow Retrieval Preregistration

## Status

**PREREGISTERED ONLY. IMPLEMENTATION NOT STARTED.**

No Phase 5B implementation may begin until the Phase 5A tested closure commit
is pinned, pushed, and the worktree is clean. `TD-JOI-009` must also satisfy its
exit criteria because retrieval cannot safely consume partially corrupted
derived memory.

## Objective

Measure whether JOI can retrieve relevant, current, provenance-complete Compact
Memory claims without false recall. Retrieval remains developer-visible shadow
output and must not enter prompts or affect responses, voice, state, or durable
memory.

## Authority Boundary

- Raw episodic evidence remains authoritative.
- Compact Memory remains derived and reconstructable.
- Retrieval selects evidence; it does not create, edit, or promote claims.
- Providers do not own retrieval, memory, identity, policy, or authorization.
- Provider/model switching cannot alter the retrieval contract.
- No provider or network call is required by the Phase 5B evaluation harness.
- Current user statements, corrections, and forgetting policies outrank every
  retrieved result.

## Frozen Inputs Before Execution

Before opening results, freeze and hash:

- the final Phase 5A closure commit and manifest;
- retrieval corpus and reference judgments;
- Compact Memory schema version and retrieval input representation;
- deterministic baseline implementation and configuration;
- query set, correction/forgetting policy records, and negative controls;
- metrics, thresholds, tie-breaking, and empty-result behavior; and
- all allowed dependency versions.

Use only synthetic or explicitly approved local data. Do not track private
production conversations.

## Corpus Requirements

The corpus must include explicit preferences, corrected facts, forgotten facts,
repeated statements, contradictions, bilingual English/Spanish queries,
technical task state, relationally relevant context, irrelevant distractors,
ambiguous queries, and queries with no supported answer.

Every relevant judgment must name current source turn IDs and policy IDs. Blind
labels must distinguish relevant, irrelevant, stale, corrected, forgotten, and
ambiguous candidates.

## Candidate Retrieval Contract

Each result must contain a stable claim ID, rank, deterministic score,
Compact Memory version, provider/model provenance of the source claim, source
turn IDs, source policy IDs, and current policy revision. Unknown fields,
missing provenance, stale policy, forgotten sources, and unsupported claims
fail closed to no result.

Ranking ties use stable claim ID ordering. Identical inputs and configuration
must produce byte-identical result ordering.

## Preregistered Metrics And Gates

Primary safety gates:

- provenance coverage: 100%;
- forgotten-memory resurrection: 0;
- superseded-fact recall: 0;
- unsupported result count: 0;
- result mutation of memory or state: 0;
- failed/corrupt input behavior: empty result with an auditable error; and
- live prompt injection: disabled.

Quality gates to freeze numerically with the labeled corpus before execution:

- precision at each supported rank;
- recall of protected safety/correction/identity facts;
- false-recall rate on irrelevant and no-answer queries;
- abstention accuracy for weak or ambiguous evidence;
- bilingual relevance parity; and
- deterministic replay agreement.

Thresholds may not be selected after viewing retrieval results. Top-1 is
probabilistic evidence, not truth, and cannot bypass provenance or policy gates.

## Failure And Adversarial Cases

Tests must cover malformed and truncated Compact Memory, hash mismatch, unknown
schema version, missing source evidence, stale policy revision, forgotten and
superseded sources, duplicate claim IDs, score ties, empty corpus, irrelevant
queries, conflicting current evidence, restart, and storage read failure.

Any failure returns no retrieval context. There is no implicit online lookup,
provider fallback, hidden retry, or use of stale cached results.

## Technical Debt Entry Review

For Phase 5B shadow evaluation specifically:

- `TD-JOI-009` is `BLOCKING` because corrupt derived input must fail closed.
- `TD-JOI-004`, `TD-JOI-005`, and `TD-JOI-010` remain deferred and do not block
  a bounded local shadow corpus.
- `TD-JOI-006`, `TD-JOI-007`, `TD-JOI-008`, and `TD-JOI-011` remain globally
  blocking for operational provider use, publication, or schema evolution, but
  do not block a provider-free, schema-frozen shadow retrieval experiment.
- `TD-JOI-001`, `TD-JOI-002`, and `TD-JOI-003` remain accepted non-blocking
  limitations with claims bounded to their recorded evidence.

No debt classification is silently resolved by Phase 5B entry.

## Exit Boundary

A Phase 5B PASS would authorize only a separately reviewed retrieval candidate
for continued shadow evaluation. It would not authorize prompt injection,
production use, publication, relational inference, graph/vector infrastructure,
autonomous action, or a change to JOI's memory authority.