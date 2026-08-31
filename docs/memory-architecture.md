# Memory Architecture

## Authority Model

Raw conversation evidence is authoritative. Summaries, graph relationships,
vector matches, salience scores, and future dream candidates are derived
retrieval aids and must never silently rewrite that evidence.

The memory layers are introduced in this order:

1. append-only episodic conversation evidence
2. compact derived summaries
3. provenance-aware NIC graph writes
4. source-linked vector entries
5. inspectable shadow retrieval
6. confidence-gated prompt injection
7. salience and non-destructive decay
8. read-only dream candidate generation

Each layer remains disabled until its own acceptance gate passes.

## Implemented Foundation

Persistent episodic memory is experimental and disabled by default:

```dotenv
ENABLE_PERSISTENT_MEMORY=false
MEMORY_MODE=session
```

Enabling durable writes requires both settings:

```dotenv
ENABLE_PERSISTENT_MEMORY=true
MEMORY_MODE=persistent
```

`MEMORY_STORE_PATH` may override the default local database at
`data/memory/episodic.sqlite3`.

Only a successfully completed user/assistant exchange is written. Both turns
are committed in one SQLite transaction with:

- stable turn and exchange IDs
- explicit user or assistant role
- complete raw content
- a timezone-aware UTC timestamp
- a schema version

Update and delete triggers protect raw turns from mutation at the database
boundary. Corrections and forgetting are separate append-only policy records;
they never pretend that original evidence did not exist. Each later policy
references the policy it supersedes. The latest policy determines the effective
view: a correction supplies replacement content, while a forget policy
suppresses effective content without physically deleting the raw turn.

The explicit inspection surface is available only when persistent memory is
configured:

```text
/memory status
/memory recent [limit]
/memory why <turn-id>
/memory correct <turn-id> <replacement>
/memory forget <turn-id> [reason]
```

`status` reports schema and record counts, `recent` shows effective state, and
`why` shows raw evidence plus the complete policy provenance chain. These
commands do not retrieve memory into the model prompt.

## Runtime Behavior

- `MEMORY OFF` clears active session context and prevents durable writes.
- `MEMORY SESSION` retains only bounded in-process conversation history.
- `MEMORY PERSISTENT` retains bounded session context and appends completed
  exchanges to the episodic store.
- A persistent-store initialization failure is logged and shown as
  `PERSISTENT (UNAVAILABLE)` while chat remains operational.
- A write failure preserves the completed response, logs the failure, and
  disables further writes for that process. There are no hidden retries.
- Persistent records are not retrieved or injected into model prompts yet.

The SQLite database contains plaintext conversation content. It is excluded
from Git, but the host filesystem remains responsible for access control,
backup protection, and deletion of the physical database.

## Compact Memory Shadow Gate

Compact Memory is independently disabled by default and requires persistent
episodic memory:

```dotenv
ENABLE_PERSISTENT_MEMORY=true
MEMORY_MODE=persistent
ENABLE_COMPACT_MEMORY=true
```

The initial `extractive-v1` summarizer is deliberately conservative. It keeps a
bounded rolling set of canonical, whitespace-normalized source excerpts rather
than generating new factual prose. This allows JOI to reject altered excerpts
deterministically as contradictions while retaining stable raw turn IDs,
update time, schema version, and summarizer version.

Updates run sequentially on a background worker after the complete exchange is
committed to episodic memory. A failed or malformed update leaves the previous
valid JSON state unchanged and is logged without blocking text or voice. An
orderly application exit flushes accepted jobs. A corrupted compact-memory file
disables only the compact layer.

Compact Memory remains shadow-only derived state. It is not injected into model
prompts, and no excerpt becomes authoritative independently of its raw turn.
`COMPACT_MEMORY_MAX_CHARACTERS` bounds the rendered state and defaults to 2000.
Existing compact state is not yet invalidated or regenerated when a source turn
is later corrected or forgotten. It may therefore retain an obsolete source
excerpt and must remain non-authoritative until policy-aware regeneration has
its own acceptance gate.

## Next Gate: NIC Graph Adapter

NIC integration should begin write-only after its actual graph interface and
schema are available for review. Until then, Compact Memory remains the only
derived layer and has no effect on live responses.

Relational continuity and adaptation remain gated behind memory correction,
inspection, and measured shadow retrieval. Their sequencing and invariants are
defined in [cognitive-roadmap.md](cognitive-roadmap.md).

## Deferred Gates

- Vector storage remains an independently disabled semantic fallback.
- Retrieval begins in shadow mode and returns empty context on failure.
- Decay changes retrieval priority, never storage retention.
- Dreaming initially emits inspectable hypotheses with no automatic commit.
