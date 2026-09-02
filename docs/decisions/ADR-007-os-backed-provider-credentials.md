# ADR-007: OS-Backed Provider Credentials

## Status

Accepted for implementation; real-key rotation and operational smoke evidence
remain pending under `TD-JOI-012`.

## Context

An ignored project-tree `.env` prevented Git publication but did not prevent
local tools or processes from reading plaintext provider credentials. Settings,
core orchestration, and provider instances also retained key strings longer
than one HTTP call required.

## Decision

- Store OpenAI and ElevenLabs credentials as separate user-scoped Windows DPAPI
  records under `%LOCALAPPDATA%\JOI\credentials`, outside the repository.
- `CredentialProvider` exposes only `get_openai_credential()` and
  `get_elevenlabs_credential()`.
- Settings contain endpoint, model, timeout, feature, and audit configuration,
  but no credential fields.
- Core passes a credential capability to a provider adapter and never receives
  a secret value.
- Each adapter validates CLOUD authorization and its official HTTPS endpoint
  before retrieving its provider-specific credential.
- Adapters do not retain returned values. Redirects are denied. Errors are
  redacted and raised without secret-bearing exception chains.
- Access audit events contain only provider, source type, success, and UTC
  timestamp. No secret or fingerprint is recorded.
- Credential administration accepts values through hidden process input only;
  command arguments and environment variables are prohibited.

DPAPI encrypts at rest for the current Windows user. It does not protect a
credential from malicious code already executing as that user. OS account
security and process trust remain required.

## Isolated Provider Broker Evaluation

A child-process broker would further reduce the number of JOI components able
to access a provider credential. It would also create a new IPC protocol for
private prompts or speech, child lifecycle and crash handling, response size
bounds, executable authentication, and cancellation. Implementing that protocol
inside this credential-storage repair would widen the safety-critical change
without frozen requirements or an authoritative threat model.

The broker is therefore not activated in this revision. Provider adapters are
the narrow credential boundary and hold a key only in a call-local variable.
Before production cloud reliance, separately preregister and test a broker with
validated operation allowlists, bounded stdin/stdout JSON, no credential in
arguments/environment, fail-closed crash behavior, and no private payload or
headers in diagnostics. A subprocess-crash secret test is not applicable until
that broker exists; it becomes a hard gate if one is introduced.

## Consequences

- Restart resolves the current DPAPI record without reloading application
  settings.
- Removing a record fails closed at the next call.
- Replacing a record changes the next call without mutating provider state.
- There is no silent fallback to another credential or cloud provider.
- Real revocation and service-identity checks remain human-authorized external
  operations and cannot be inferred from unit tests.