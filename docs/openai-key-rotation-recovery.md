# OpenAI Key Rotation And Recovery

## Scope

This procedure applies to JOI's OpenAI Compact Memory provider. It preserves
JOI's provider-independence boundary: the provider may generate candidates, but
it never owns JOI state, memory, validation, publication, or fallback policy.

Never place a key in source control, command-line arguments, logs, chat,
benchmark inputs, memory, telemetry, exceptions, or evidence artifacts. The
provider necessarily holds the active credential transiently in process memory
to authorize a request; that credential must never enter JOI's durable memory.

## Planned Rotation

1. Set runtime CLOUD authorization to OFF before changing credentials.
2. Revoke the old key at the provider before relying on the replacement.
3. Create a least-privilege replacement using the provider's approved account
   and project controls.
4. Store it only in the ignored local `.env` or an approved external secret
   store. Do not type it into a shell command or commit it.
5. For an active provider instance, call `reload_api_key(replacement)` through
   an authorized local control path. Reloading an empty value deliberately
   places the provider in fail-closed missing-credential state.
6. Keep CLOUD OFF until the operator explicitly authorizes a health request.
7. When authorized, perform one health request. Do not retry silently and do
   not fall back to another provider after authentication failure.
8. Confirm that logs, Compact Memory state, evaluation reports, telemetry, and
   benchmark artifacts contain no key material.

Editing `.env` does not mutate an already-running provider instance. The active
instance must be reloaded explicitly or the process must be restarted. This
prevents accidental ambiguity about which credential is in use.

## Revocation Or Suspected Exposure

1. Set CLOUD OFF immediately.
2. Revoke the exposed key at the provider.
3. Preserve only sanitized error and audit metadata; never preserve the key.
4. Clear the running provider with `reload_api_key("")` when an authorized
   local control path is available, or stop the process.
5. Search tracked and non-ignored files for credential patterns.
6. Inspect local logs and generated artifacts without printing secret values.
7. Create and load a replacement by following Planned Rotation.
8. Record operator confirmation, time, affected provider, and validation
   outcome. Record no credential fingerprint unless an approved policy defines
   a non-sensitive identifier.

## Failure And Recovery Contract

- Missing, revoked, expired, or rejected credentials fail closed.
- Authentication failure makes no Compact Memory candidate write.
- The previous valid Compact Memory remains authoritative.
- A rejected credential does not invoke local or alternate-provider fallback.
- Conversation and episodic persistence remain available.
- Errors are operator-visible and redact the credential used by that request.
- Recovery requires explicit replacement and explicit CLOUD authorization.
- No hidden retry may reuse a stale key.

## Verification

Automated provider tests cover:

- revoke to replace to in-process reload;
- replacement Authorization header use without stale-key reuse;
- missing-key refusal before opening a request;
- simulated revoked-key rejection;
- no fallback after authentication failure;
- redacted exceptions and absent log leakage;
- no candidate-memory mutation; and
- no credential in persisted evaluation artifacts or provider telemetry.

These deterministic tests do not prove the provider-side revocation service,
account policy, or production secret-store lifecycle. `TD-JOI-008` remains open
until an explicitly authorized end-to-end exercise satisfies its exit criteria.