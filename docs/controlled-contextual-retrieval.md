# Controlled Contextual Retrieval

Phase 5C v2 permits a narrow, human-gated retrieval path. It is disabled by
default and requires persistent memory, graph memory, and graph retrieval:

```dotenv
ENABLE_PERSISTENT_MEMORY=true
MEMORY_MODE=persistent
ENABLE_GRAPH_MEMORY=true
ENABLE_GRAPH_RETRIEVAL=true
ENABLE_CONTEXTUAL_RETRIEVAL=true
```

The terminal workflow is deliberately explicit:

```text
/context propose <query>
/context inspect <approval-id>
/context approve <approval-id>
/context chat <approval-id> <same query>
```

Approval is held in memory, bound to the exact query hash and retrieval
receipt, and consumed once. Restarting JOI invalidates outstanding approvals.
Only effective, source-linked candidate content is included. It is rendered as
untrusted reference data, never as instructions, and it cannot authorize an
external or real-world action.

Without an approval ID, `chat()` remains unchanged. The approved reference is
temporary and is not added to session memory or durable memory. Provider and
network calls remain unrelated to this local retrieval path, and live
retrieval remains disabled unless the explicit feature flags are enabled.