# Workspace Layout

JOI's Git repository and its local runtime assets are intentionally separate.
This keeps large model files, virtual environments, logs, generated audio, and
durable local memory outside the tracked source tree.

```text
D:\JOI\
|-- .venv\                  # Main Python environment; local only
|-- .venv-kokoro\           # Isolated Kokoro environment; local only
|-- .venv-tts\              # TTS benchmark environment; local only
|-- models\                  # Downloaded model weights; local only
|-- JOI_2_0\
|   `-- JOI_2_0\            # Git repository root
|       |-- .env.example     # Non-secret configuration template
|       |-- data\            # Runtime outputs ignored by Git
|       `-- ...
`-- JOI_2_0_phase01.zip      # Historical archive; not the active repository
```

Run source-control commands from `D:\JOI\JOI_2_0\JOI_2_0`. The default
settings resolve the shared runtime directory as `D:\JOI`; non-standard
layouts must explicitly set the path overrides in `.env`.

## Credential boundary

Never place provider keys in `.env`, shell environment variables, the workspace
tree, model folders, benchmark packets, or command history. `.env` is
non-secret configuration only and is ignored by Git. Provider credentials are
stored separately as user-scoped Windows DPAPI records and managed only through
`credential_admin.py`.

Before sharing or publishing, run the full test suite and a redacted
credential-shaped-string scan. Report only file paths or counts from that scan;
never print a matching value. Test fixtures must use obviously fake tokens that
cannot be mistaken for a provider credential.
