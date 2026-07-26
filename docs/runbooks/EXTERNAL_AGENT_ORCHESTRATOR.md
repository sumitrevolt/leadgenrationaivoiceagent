# Runbook — External Agent Orchestrator (Cursor + Claude missions)

Decision record: `docs/adr/ADR-148-external-agent-orchestrator.md`.
Flag: `EXTERNAL_AGENT_ORCHESTRATOR` (default `0`, fully inert).

## 1. What it is / is not

| Is | Is not |
|----|--------|
| A mission ledger with leases, path ownership, risk lanes, evidence and review separation | A second Owner OS, dispatcher or agent registry |
| An extension of `app/dev_control` + OpenClaw Stage A observe | A shell/deploy/calling/billing executor |
| Code-enforced acceptance of agent result manifests | A place where an LLM statement advances state |

Owner OS remains the sole action authority. OpenClaw remains the orchestration
edge and only gains two **GREEN read-only** commands.

Honest naming: this is a **safe orchestration foundation**. It records and
validates missions; it does **not** autonomously invoke Cursor or Claude.

## 2. Enable (local / staging first)

```bat
set EXTERNAL_AGENT_ORCHESTRATOR=1
.venv\Scripts\python.exe -m pytest tests/test_external_agent_orchestrator.py tests/test_external_agent_multiprocess.py -q
```

Admin cockpit: `/dev-control` → "External agent missions" card
(the card says `EXTERNAL_AGENT_ORCHESTRATOR is OFF` until the flag is set).

Production flip is **AMBER** — owner authorisation required. It changes no
runtime behaviour on its own (no scheduler job, no worker, no outbound path).

## 3. Mission loop (happy path)

```text
POST /api/dev-tasks/missions                 # create (RED refused here)
POST /api/dev-tasks/missions/{id}/preflight  # returns the executor packet
POST /api/dev-tasks/missions/{id}/claim      # single-owner lease (cross-process CAS)
POST /api/dev-tasks/missions/{id}/start
POST /api/dev-tasks/missions/{id}/heartbeat  # keep the lease alive
POST /api/dev-tasks/missions/{id}/result     # manifest; scope breach = BLOCKED
POST /api/dev-tasks/missions/{id}/review     # different agent, must cite evidence
POST /api/dev-tasks/missions/{id}/advance    # PR_OPEN → CI_RUNNING → MERGE_QUEUED → MERGED
GET  /api/dev-tasks/missions/{id}/rollback   # rollback package (never executes)
```

## 4. Persistence and cross-process correctness

Correctness boundary is **not** `threading.RLock`.

| Backend | When | Topology |
|---------|------|----------|
| Redis (`REDIS_URL` / `EXTERNAL_MISSION_REDIS_URL`) | preferred when reachable | multi-container / multi-host |
| portalocker file locks under `data/external_missions/.locks/` | fallback | processes sharing `EXTERNAL_MISSION_DIR` |

Production evidence: `docker-compose.vps.yml` bind-mounts `./data:/app/data` into
app, worker, scheduler, worker-heavy and worker-video — FileLock CAS on that path
is shared across those containers on one VPS host. Redeploy preserves `./data`.
Windows Cursor and Claude Code only share state when they use the same
`EXTERNAL_MISSION_DIR` (or the same Redis).

## 5. Recovery

| Symptom | Action |
|---------|--------|
| Worker died mid-mission | `POST /api/dev-tasks/missions/recover-stale` |
| Mission wedged | `POST /missions/{id}/retry` |
| Wrong mission | `POST /missions/{id}/cancel` |
| Need to undo shipped work | `GET /missions/{id}/rollback` (manual runbook) |
| Kill everything | unset `EXTERNAL_AGENT_ORCHESTRATOR` |

Event audit: `data/external_missions/events.jsonl` (redacted, append-only).

## 6. OpenClaw (Owner Copilot)

GREEN read-only: `external.missions`, `external.mission_status`.
No AMBER/RED command is added. Workforce stays 31 agents.

## 7. Owner decision — branch ruleset hardening (AMBER)

Classic `branches/main/protection` returns 404, but an **active repository
ruleset** already protects `main` (id `19718692`): required checks
`Lint + syntax + secrets`, `prod_check + pytest`, `harness real-redis integration`,
strict up-to-date, force-push/deletion blocked, no bypass actors.

Optional hardening (add `test` + `GitGuardian Security Checks`, enable
conversation resolution) is prepared in
`docs/runbooks/BRANCH_PROTECTION_AMBER_PACKAGE.md` — **not applied** without
owner authorization.
