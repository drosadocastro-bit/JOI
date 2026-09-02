# Phase 5C Personalized PageRank Shadow Retrieval Preregistration

## Status

**PREREGISTERED INPUTS ONLY. RETRIEVAL IMPLEMENTATION AND EXECUTION NOT STARTED.**

Phase 5C may not produce retrieval results until the source/query corpus and
human relevance labels are complete, frozen, and hash-verified. Phase 5B remains
closed under its write-only contract; Phase 5C cannot modify its artifacts.

## Bounded Objective

Evaluate whether JOI can produce deterministic, policy-filtered,
provenance-linked associative-memory candidates with Personalized PageRank
(PPR) in shadow mode without changing prompts, responses, provider calls,
network calls, or authoritative episodic memory.

Retrieval may surface evidence. It does not create truth, authority, or
permission. Graph retrieval returns candidates, not memory facts. Historically
supported does not mean currently retrievable.

## Entry Gate

Required before implementation:

- Phase 5B closure artifacts and hashes verify against the Phase 5C entry pin.
- The complete baseline passes with exactly 239 tests.
- all Phase 5B execution-manifest entries verify;
- Phase 5B closure inputs remain byte-identical;
- runtime retrieval defaults remain false;
- this preregistration and the benchmark corpus are frozen before retrieval
  output exists;
- a human completes and freezes labels before retrieval output exists; and
- no graph retrieval implementation is present at freeze time.

The Phase 5B closure is currently hash-pinned but not committed: repository HEAD
is `14164dc` and the Phase 5B files are in the dirty worktree. This is an explicit
audit limitation. Any Phase 5B byte change invalidates 5C entry until reviewed
and re-pinned.

## Authority And Isolation Contract

- `ENABLE_GRAPH_RETRIEVAL=false` is the required runtime default.
- Retrieval is shadow-only and requires graph memory plus persistent mode.
- Retrieval candidates never enter a live prompt or response path.
- Retrieval influence and injection counts remain zero.
- Providers, cloud access, networking, embeddings, vectors, and fallback
  retrieval are prohibited.
- Retrieval queries do not mutate graph, episodic memory, policies, or source
  turns and do not train or reinforce ranking.
- No edge decay, reinforcement, graph learning, relational inference, salience,
  personality adaptation, callback, consolidation, MCP, or action is authorized.
- Raw episodic turns and policy records remain authoritative.

Expected failure behavior is empty shadow retrieval plus normal conversation.
There is no hidden retry, stale-cache fallback, or online lookup.

## Query And Seed Contract

The bounded explicit pattern definitions and canonicalization semantics from
Phase 5B are applied to the current user turn only through a dedicated
read-only query extractor. The Phase 5B write extractor itself requires a
completed user/assistant exchange and must not be called with fabricated
assistant content merely to satisfy that API. A query receipt records:

- `query_id` and `query_turn_id`;
- stable query hash, but no prompt injection;
- `seed_entity_ids` in stable node-ID order;
- unresolved explicit surface forms;
- `extractor_version`; and
- source/query provenance.

Aliases use the Phase 5B deterministic canonicalization. Only exact canonical
node resolution is allowed. Zero seeds and unknown entities return an empty
result. Retrieval cannot write unknown entities into the graph or infer hidden
entities to manufacture a seed.

## Effective-Memory View

Policy resolution occurs before candidate publication:

1. Logical forgetting makes every source from the forgotten target turn
   ineligible while preserving historical lineage for inspection.
2. Correction suppresses the original target turn and deterministically
   re-extracts the explicit replacement content as effective evidence.
3. Unchanged explicit entities in replacement content, such as Project Atlas,
   remain eligible through replacement provenance.
4. Superseded entities absent from replacement content, such as Madrid, remain
   historical and ineligible.
5. Replacement entities, such as Lisbon, may be eligible only with correction
   policy provenance.
6. A node is eligible only if it has at least one current effective source.

The frozen safety cases require Luna and green tea to be ineligible after
forgetting, Madrid to be ineligible after correction, Lisbon to be eligible as
the replacement, and Project Atlas to remain eligible.

## Frozen PPR Definition

- algorithm: power-iteration Personalized PageRank;
- graph: schema-v1 `co_occurs` edges treated as bidirectional;
- transition weight: stored edge weight after effective-source filtering;
- personalization: uniform probability across resolved eligible seed nodes;
- damping factor: `0.85`;
- convergence tolerance: L1 delta `1e-12`;
- maximum iterations: `100`;
- dangling mass: redistributed according to personalization;
- output depth: `K=3` filtered non-seed candidates;
- score representation: IEEE-754 double serialized to 15 significant digits;
- ordering: descending score, then ascending stable node ID;
- randomness: none;
- mutation during ranking: prohibited.

Empty graphs, no eligible seeds, disconnected seeds with no non-seed candidate,
and non-convergence produce no published candidates. Non-convergence is recorded
as a rejection/failure reason and cannot expose partial ranking output.

## Candidate Contract

Raw PPR results and post-policy results are measured separately. Publication of
a shadow candidate requires:

- non-seed node unless a benchmark case explicitly permits seed return;
- at least one current effective source reference;
- explicit extraction status;
- complete exchange, turn, and policy provenance;
- no forgotten or superseded-only evidence;
- deterministic alias and evidence-reference collapse; and
- no duplicate node ID.

Every rejected candidate records a stable reason code. Required codes include
`QUERY_SEED`, `FORGOTTEN_SOURCE`, `SUPERSEDED_SOURCE`, `NO_EFFECTIVE_SOURCE`,
`UNSUPPORTED_STATUS`, `DUPLICATE_ALIAS`, `MALFORMED_PROVENANCE`, and
`PPR_NON_CONVERGENCE`.

## Receipt And Explainability Contract

Each attempt atomically writes a content-bounded developer receipt containing:

- receipt ID and query metadata;
- graph snapshot SHA-256;
- resolved seeds and unresolved surfaces;
- frozen PPR parameters, iterations, and convergence state;
- raw ranked candidates and scores;
- filtered and rejected candidates with policy reason codes;
- effective and historical source references;
- contributing seed IDs and deterministic predecessor/neighborhood evidence;
- latency in milliseconds;
- retrieval count and influence count (`0`); and
- prompt, provider, network, and durable-state deltas.

Inspection may explain a receipt or candidate but creates no conversation read
path. Full path attribution is explanatory graph evidence, not a causal or truth
claim.

## Frozen Corpus And Human Labels

The corpus uses synthetic local statements only. It includes direct, one-hop,
two-hop, unrelated, ambiguous, unknown, forgotten, superseded, corrected,
repeated, high-degree hub, sparse, disconnected, duplicate-alias,
contradictory-history, and unsupported bilingual surface cases. Cases where the
correct result is empty are first-class acceptance cases.

Before any retrieval output is opened, a human reviewer must classify expected
candidates for every query as `relevant`, `acceptable_secondary`, `irrelevant`,
`harmful_stale`, or `forbidden`; mark whether empty retrieval is expected; cite
source turn and policy IDs; identify themselves; and record UTC review time.
Semantic relevance and source support are separate judgments. Unresolved or
disputed labels remain preserved and force an INCONCLUSIVE decision.

## Metrics

Report raw-PPR and post-policy-filter metrics separately:

- Recall@3 and Precision@3;
- mean reciprocal rank;
- irrelevant retrieval rate;
- false recall rate;
- forbidden/stale retrieval rate;
- correction and forgetting adherence;
- provenance coverage;
- empty-context correctness;
- deterministic replay byte match;
- hub contamination rate; and
- median and p95 local retrieval latency.

## Frozen Decision Thresholds

A PASS requires all of:

- post-filter Recall@3 `>= 0.80`;
- post-filter Precision@3 `>= 0.85`;
- post-filter mean reciprocal rank `>= 0.75`;
- irrelevant retrieval rate `<= 0.10`;
- false recall rate `<= 0.05`;
- forbidden/stale retrieval rate `= 0`;
- correction adherence `= 1.0`;
- forgetting adherence `= 1.0`;
- provenance coverage `= 1.0`;
- empty-context correctness `= 1.0`;
- deterministic replay byte match `= true`;
- hub contamination rate `<= 0.10`;
- behavior delta and prompt delta `= false`;
- retrieval injection and influence counts `= 0`;
- provider and network call counts `= 0`;
- durable episodic and Phase 5B graph state byte deltas `= 0`;
- every failure control returns empty shadow retrieval while conversation
  continues normally;
- runtime/live retrieval remains disabled; and
- independent human result review is complete.

Latency is reported, not a PASS gate, because machine load is not frozen. A FAIL
occurs when any safety invariant fails or a completed valid evaluation misses a
numerical quality threshold. INCONCLUSIVE applies when labels/review are
incomplete, manifests do not verify, the environment cannot execute the frozen
contract, or evidence is missing. Thresholds may not be tuned after results are
opened.

## Failure Controls

Required controls: corrupt graph, missing graph, malformed seed extraction,
unknown schema, forced PPR non-convergence, absurd/high-degree hub, zero eligible
candidates, all candidates policy-filtered, stale correction record, duplicate
policy record, and interrupted receipt write. Each must yield an auditable empty
shadow result and leave normal conversation behavior intact.

## Closure Boundary

If every gate passes, Phase 5C may claim only:

> Phase 5C demonstrates that JOI can produce deterministic, policy-filtered,
> provenance-linked associative-memory candidates using Personalized PageRank
> in shadow mode under the tested conditions.

It does not establish that retrieved memories are safe or beneficial for live
prompt use. Phase 5D graph/vector/hybrid comparison requires a separate frozen
entry decision and is not authorized here.
