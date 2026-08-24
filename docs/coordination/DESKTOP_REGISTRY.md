# Desktop App Registry — local agent coordination

> **Machine-readable source of truth:** [`desktop_registry.json`](./desktop_registry.json) — the Coordination Hub projects this file into its read-only view (`/app/owner` → Coord Hub). Edit the JSON, not this prose, when apps change.
> Status: LG-10 Cursor Builder deliverable under **A-20260813-CURSOR** (read-only registry; enrollment changes = Owner OS).

## Why this file exists

Five desktop agent apps work on the same project. Each needs: its own isolated project/worktree, a bus channel for progress/results, a single-writer lock token, a harness contract, and a heartbeat. This registry documents who-is-who so the master coordinator (External Agent Orchestrator + Owner OS + Buzz relay + buzzlock) can treat each app consistently without hardcoding app names in five places.

## Registered apps (6)

| id | name | project | channel | buzzlock TOOL | harness | heartbeat |
|----|------|---------|---------|---------------|---------|-----------|
| `freebuff` | FreeBuff Desktop | repo — dedicated mission worktree | `#build` / `#dev` | `FREEBUFF` | GUI in-process (no CLI) | manual / hub HMAC |
| `android` | Android Studio | its own Gradle project | `#dev` | — (pending `ANDROID`) | GUI + Gemini assistant (no CLI) | none today |
| `opencode` | OpenCode Desktop | repo — dedicated worktree | `#dev` | `OPENCODE` | `opencode run --format json` + GUI | hub HMAC |
| `cursor` | Cursor Desktop | repo — dedicated worktree | `#build` / `#dev` | `CURSOR` | `cursor-agent -p` + GUI | hub HMAC |
| `hermes` | Hermes Desktop | repo — dedicated worktree | `#build` / `#dev` | `HERMES` | desktop GUI + headless CLI (MCP-coordinated) | hub HMAC |
| `buzz` | Buzz Desktop | bus owner — local relay | all (`#build #dev #admin #staff-pulse`) | — (bus role) | GUI + relay | hub buzz webhook |

> **Naming disambiguation (important):** the registry id `hermes` refers to the **Hermes Desktop** coordination app above — a repo-bound coding agent bus participant. It is **NOT** the same as the internal STAFF **Hermes 🛰️** infra watchdog (`app/platform/infra_handler.py`), nor the external **Hostinger Managed Hermes** cloud agent (`hostinger_hermes` prefix). Those two live in different namespaces (team STAFF roster / external cloud) and are unaffected by this registry row. `HERMES` (buzzlock TOOL) and tool id `hermes` (hub HMAC) are enrolled alongside the other coding apps.

## Rules

1. **Registry = doc, not control.** Mutations (mission create, lease claim, lock acquire) live on their existing surfaces: `/api/dev-tasks/missions`, Owner OS, buzzlock. The Hub never mutates (projection only).
2. **Each app operates through its own project.** Repo apps (FreeBuff / OpenCode / Cursor) get a dedicated isolated worktree per mission from a recorded base SHA. Android Studio owns a separate Gradle project — it shares neither the repo tree nor its locks.
3. **buzzlock TOOL tokens must match `scripts/buzzlock.py` `TOOLS`.** `FREEBUFF` / `OPENCODE` / `CURSOR` / `HERMES` are enrolled today. `ANDROID` is documented-but-pending: `--tool ANDROID` will be rejected until Owner OS adds it to `TOOLS` (a separate change — not in this registry's scope). Buzz has no lock role; it is the bus owner.
4. **Hub HMAC allowlist is separate from buzzlock.** `app/platform/coordination_hub_auth.py` `_KNOWN_TOOLS` gates heartbeat/webhook attestation. `android` is not enrolled there either — `status: documented` until Owner OS decides.
5. **Status field** (`registered` vs `documented`) is the honest split: `registered` = lock/hub enrolled today; `documented` = in the registry, enrollment pending Owner OS.
6. **No secrets, no PII, no customer data** in this file or its JSON — paths and tokens only.

## How the Hub projects it

- `app/platform/coordination_desktop_registry.py` loads `desktop_registry.json` (never raises; missing/invalid → `ok:false`, `apps:[]`).
- `app/platform/coordination_hub.py::snapshot()` includes a `desktop_registry` slice (inert-empty when `COORDINATION_HUB_ENABLED=0`).
- `frontend/coordination_hub.html` renders the slice read-only on the Aaj tab.

## Verify

```bash
.venv\Scripts\python.exe -m pytest tests/test_desktop_registry.py -q
.venv\Scripts\python.exe scripts/prod_check.py
```
