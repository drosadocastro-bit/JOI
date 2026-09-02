# Tooling Data Deny Policy

This policy is independent of Git publication controls. Local tools must not
read, index, attach, summarize, upload, or recursively scan these paths:

- `.env*`;
- `.credentials/`, `credentials/`, `secrets/`, and `secret-cache/`;
- `data/memory/**`, `data/snapshots/**`, and `data/logs/**`;
- `*.dmp`, `*.dump`, `*.core`, and `crash-reports/`.

The same patterns are recorded in `.ignore` and `.copilotignore`. Tools that do
not honor those files must be configured separately or restricted to an
explicit allowlist of source and documentation paths. These files do not
sandbox arbitrary local processes and are not a substitute for OS access
control or user-scoped DPAPI encryption.

Credential values must never be passed through command arguments, environment
variables, global machine configuration, shell history, clipboard automation,
logs, diagnostics, telemetry, memory artifacts, crash dumps, retry objects, or
exception chains.