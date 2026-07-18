# Context Hygiene Policy — temporary artifacts & operational scripts

_Added 2026-07-18 (ai-firstify). Goal: keep `git status` and agent context trustworthy WITHOUT hiding reusable tools or losing evidence._

## The rule of thumb
A file is one of five things. Put it where its kind belongs:

| Kind | Example | Where it goes | Tracked? |
|------|---------|---------------|----------|
| Reusable tool | canary runner, deploy verifier, recovery util | `scripts/canary/` or `scripts/` with a stable name + header doc | ✅ yes |
| One-off script | `_tmp_poll_dep.bat`, session-specific probe | `scripts/_tmp_*` or `scripts/_debug/` | ❌ ignored |
| Generated output | `*.log`, `_out.txt`, exit-code/PID dumps, pytest capture | `artifacts/local/` or next to the tool as `_canary_*.log` | ❌ ignored |
| Durable evidence | prod verification, incident/compliance findings | a concise `.md` under `docs/` (raw capture removed after) | ✅ (the .md) |
| Cache/build | `__pycache__`, `.venv`, `node_modules`, worktrees | — | ❌ ignored |

## Conventions
- **Reusable canary/diagnostic tools are TRACKED.** Never blanket-ignore `scripts/_canary_*` — that hides safety-critical tooling. Only canary *outputs* (`scripts/_canary_*.log`, `_canary_*_out.txt`, `_canary_*.txt`) are ignored. Promote a proven `_canary_*` script to a stable name under `scripts/canary/`.
- **`_tmp_` prefix = disposable, ignored.** If you keep re-running it, it isn't `_tmp_` — rename and track it.
- **`artifacts/local/`** is the designated ignored scratch dir for local diagnostics + generated output. Prefer it over scattering files in the repo root.
- **Root-scoped output ignores** (`/*_exit.txt`, `/pytest_*.txt`, `/*_result.txt`, `/forensics_*.txt`) only catch repo-root captures — they never hide nested tracked evidence.
- **Durable evidence → Markdown first.** Convert raw captures to a short `docs/…md` (redact secrets, phone numbers, payment IDs) before deleting/ignoring the raw file.
- **Never** commit secrets, `.env`, private keys, customer PII/transcripts, or payment identifiers. `scripts/check_secrets.py` (`/verify`) is the gate.
