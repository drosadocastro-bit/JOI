# Phase 5B Write-Only Graph Memory Preregistration

## Status

**CONTRACT FROZEN BEFORE BEHAVIORAL IMPLEMENTATION.**

Phase 5B may begin only after the separate entry authorization records a PASS
for Compact Memory artifact recovery and closes `TD-JOI-009`. This document
authorizes no retrieval, prompt injection, or production use.

## Question

> Can JOI construct an inspectable, provenance-linked associative graph from
> completed exchanges without changing conversation behavior?

## Non-Authority Contract

- A user/assistant exchange is source evidence, not automatically truth.
- Extractor output is a candidate representation, not evidence or truth.
- A graph node is an association/index structure, not evidence or truth.
- A graph edge records measured co-occurrence, not evidence or truth.
- JOI owns graph state, validation, storage, and inspection.
- No LLM, provider, or NIC application owns JOI graph state.
- Corrections and logical forgetting in episodic/effective memory remain
  authoritative over graph lineage.
- Graph contents cannot affect prompts, responses, voice, identity, policy, or
  authorization in this phase.

## Feature And Storage Boundary

- `ENABLE_GRAPH_MEMORY=false` by default.
- Graph Memory additionally requires persistent memory.
- Disabled mode creates no graph worker, file, or write.
- Enabled mode is write-only except explicit developer/operator inspection.
- One completed exchange is one atomic graph transaction.
- Empty and missing graph artifacts are valid.
- Unknown schema versions and corrupt artifacts fail closed.
- Failed extraction or storage cannot fail normal conversation or episodic
  persistence.

## Explicitly Prohibited

This slice contains no Personalized PageRank, spreading activation, graph
retrieval, vector embeddings, vector fallback, edge decay, salience learning,
relational inference, prompt injection, live callbacks, automatic ambiguous
entity merging, graph-based adaptation, dreaming, MCP, or actions.

## Minimal NIC-Compatible Semantics

The JOI workspace contains no authoritative NIC source tree or published graph
schema. Therefore Phase 5B imports no NIC code and makes no verified wire-format
compatibility claim. It reimplements only these bounded semantics requested for
future compatibility:

- `GraphEvidenceRef`: source exchange, source turns, source policies, timestamp;
- `GraphNode`: canonical entity plus aliases and source-linked observations;
- `GraphEdge`: ordered node pair plus source-linked `co_occurs` observations;
- `GraphMemoryStore`: JOI-owned atomic durable state.

The implementation must evolve independently and use no NIC network or runtime
dependency. Before any NIC interoperability claim, compare these primitives to
an authoritative versioned NIC contract and record the source commit/schema.

## Frozen Schema Version 1

### GraphEvidenceRef

Required fields:

- `exchange_id`
- non-empty `turn_ids`
- matching `policy_ids`, including `null`
- UTC `observed_at_utc`
- `suppressed` boolean

### EntityCandidate

Required fields:

- deterministic normalized `entity_id`
- exact `surface_form`
- `entity_type`: `person`, `project`, `concept`, `place`, `preference`,
  `fact`, or `task_topic`
- one `GraphEvidenceRef`
- `extractor_version`
- `status`: `explicit` only

Inferred candidates, unsupported surface forms, hidden emotional-state claims,
unknown fields, malformed Unicode, duplicate conflicting IDs, and missing
provenance are rejected. Sparse input may yield zero candidates.

### GraphNode

Required fields:

- `schema_version = 1`
- `node_id`
- deterministic `canonical_label`
- `entity_type`
- sorted unique `aliases`
- sorted unique `source_refs`
- `first_seen_utc`
- `last_seen_utc`
- `observation_count`

Observed explicit source, extracted representation, and any future derived
metadata remain distinguishable. Version 1 stores no inferred metadata and no
importance/confidence field. Ambiguous labels of different types are not
merged.

### GraphEdge

Required fields:

- `schema_version = 1`
- stable `edge_id`
- lexically ordered `source_node_id` and `target_node_id`
- `relation = "co_occurs"`
- integer `weight`
- sorted unique `source_exchange_ids`
- `first_seen_utc`
- `last_seen_utc`

Weight equals unique contributing completed exchanges. Replay cannot inflate
it. Weight does not mean truth, confidence, causality, emotion, importance, or
preference strength. No edge may exist without source evidence.

### GraphState

Required fields:

- `schema_version = 1`
- `extractor_version`
- sorted `processed_exchange_ids`
- node map keyed by `node_id`
- edge map keyed by `edge_id`
- `updated_at_utc`

Canonical serialization uses UTF-8 JSON, sorted keys, stable list ordering, and
a trailing newline.

## Deterministic Extraction Contract

The initial provider-free extractor uses explicit, auditable patterns only.
It may recognize direct names, projects, places, durable preferences, durable
facts, and tasks/topics whose complete surface form occurs in a source turn.
It does not infer attributes or hidden states. Canonical IDs use Unicode NFKC,
case folding, whitespace normalization, entity type, and SHA-256 truncation.

Every candidate is independently validated against the completed exchange.
Malformed extractor output discards the complete graph update.

## Corrections And Forgetting

Version 1 stores source policy references and a suppression marker so future
recomputation remains possible. Historical lineage may remain, but suppressed
evidence cannot be treated as current. There is no retrieval path, and thus no
suppressed graph content can affect behavior. Version 1 performs no destructive
cleanup or automatic edge recomputation after policy changes.

Future work must preregister superseded-source suppression, logical forgetting,
edge recomputation, and historical audit preservation before activation.

## Inspection Only

Allowed commands:

- `/memory graph status`
- `/memory graph node <id>`
- `/memory graph recent [limit]`
- `/memory graph why <node-or-edge-id>`

Inspection is source-linked and returns no retrieval context. There is no graph
query or retrieval command.

## Observability

Each attempted exchange records content-free metadata: exchange ID, extracted,
accepted and rejected counts, node and edge creates/updates, rejection reasons,
write latency, schema version, and extractor version. Logs and receipts contain
no conversation content or secrets.

## Frozen Evaluation Gates

- human-reviewed extraction precision: 100% on the frozen corpus;
- unsupported entity rate: 0;
- current source-provenance coverage: 100%;
- duplicate replay inflation rate: 0;
- deterministic replay byte match: 100%;
- malformed-input and graph-write survival: 100%;
- correction/forgetting lineage preservation: 100%;
- behavior delta graph ON versus OFF: 0;
- prompt delta graph ON versus OFF: 0;
- retrieval count: 0; and
- provider/network calls: 0.

Any provenance failure, unsupported entity, partial transaction, forgotten
content presented as current, prompt delta, behavior delta, retrieval, or
provider call is a hard failure.

## Exit Claim

> Phase 5B proves only that JOI can construct an inspectable,
> provenance-linked associative graph from completed exchanges without changing
> conversation behavior. It does not prove retrieval quality, memory relevance,
> factual truth, relational understanding, or cognitive continuity.

> The graph may encode association. It does not create evidence, truth,
> identity, or authority.