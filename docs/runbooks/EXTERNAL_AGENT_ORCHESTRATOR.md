# Runbook — External Agent Orchestrator (Cursor + Claude missions)

Decision record: `docs/adr/ADR-145-external-agent-orchestrator.md`.
Flag: `EXTERNAL_AGENT_ORCHESTRATOR` (default `0`, fully inert).

## 1. What it is / is not

| Is | Is not |
|----|--------|
| A mission ledger with leases, path ownership, risk lanes, evidence and review separation | A second Owner OS, dispatcher or agent registry |
| An extension of `app/dev_control` + OpenClaw Stage A observe | A shell/deploy/calling/billing executor |
| Code-enforced acceptance of agent result manifests | A place where an LLM statement advances state |

Owner OS remains the sole action authority. OpenClaw remains the orchestration
edge and only gains two **GREEN read-only** commands.

## 2. Enable (local / staging first)

```bat
set EXTERNAL_AGENT_ORCHESTRATOR=1
.venv\Scripts\python.exe -m pytest tests/test_external_agent_orchestrator.py -q
```

Admin cockpit: `/dev-control` → "External agent missions" card
(the card says `EXTERNAL_AGENT_ORCHESTRATOR is OFF` until the flag is set).

Production flip is **AMBER** — owner authorisation required. It changes no
runtime behaviour on its own (no scheduler job, no worker, no outbound path).

## 3. Mission loop (happy path)

```text
POST /api/dev-tasks/missions                 # create (RED refused here)
POST /api/dev-tasks/missions/{id}/preflight  # returns the executor packet
POST /api/dev-tasks/missions/{id}/claim      # single-owner lease
POST /api/dev-tasks/missions/{id}/start
POST /api/dev-tasks/missions/{id}/heartbeat  # keep the lease alive
POST /api/dev-tasks/missions/{id}/result     # manifest; scope breach = BLOCKED
POST /api/dev-tasks/missions/{id}/review     # different agent, must cite evidence
POST /api/dev-tasks/missions/{id}/advance    # PR_OPEN → CI_RUNNING → MERGE_QUEUED → MERGED
GET  /api/dev-tasks/missions/{id}/rollback   # rollback package (never executes)
```

Rules the code enforces (not conventions):

- Executor may only drive RUNNING/IMPLEMENTED/TESTING/REVIEW_REQUIRED/BLOCKED.
- Reviewer must differ from executor and must attach citations.
- Changed files outside `allowed_paths`, or inside protected paths
  (`app/voice_agent/`, `app/telephony/`, `app/billing/`, `.env`,
  `alembic/versions/`, deploy workflows, `docker-compose.vps.yml`) → BLOCKED.
- Two live missions cannot share a path, branch or worktree.
- AMBER stops at `OWNER_DECISION_REQUIRED` before MERGE_QUEUED/MERGED/deploy.
- MERGED/VERIFIED/COMPLETE require result + review (+ tests, + rollback plan).

## 4. Recovery

| Symptom | Action |
|---------|--------|
| Worker died mid-mission | `POST /api/dev-tasks/missions/recover-stale` → expired leases become `FAILED_RETRYABLE` with evidence |
| Mission wedged | `POST /missions/{id}/retry` (respects `retry_policy.max_retries`, then `FAILED_TERMINAL`) |
| Wrong mission | `POST /missions/{id}/cancel` |
| Need to undo shipped work | `GET /missions/{id}/rollback` → run the documented plan manually |
| Kill everything | unset `EXTERNAL_AGENT_ORCHESTRATOR` → API 503, OpenClaw reports `enabled:false` |

Event audit: `data/external_missions/events.jsonl` (redacted, append-only).

## 5. OpenClaw (Owner Copilot)

GREEN read-only: `external.missions`, `external.mission_status`.
No AMBER/RED command is added. Workforce stays 31 agents.

## 6. Owner decision pending — branch protection

Verified 2026-07-26 with `gh api repos/sumitrevolt/leadgenrationaivoiceagent/branches/main/protection`
→ **404 "Branch not protected"**, while `.github/workflows/auto-merge.yml` can flip
GitHub auto-merge on any PR labelled `auto-merge`. That means auto-merge has no
required-check floor today.

This is a repo-configuration change (AMBER) — **not executed by the agent**.
Exact command for the owner to run:

```bash
gh api -X PUT repos/sumitrevolt/leadgenrationaivoiceagent/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Gate (import + prod_check + lint)", "test"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Verify afterwards with the same GET; confirm the exact check names from a recent
run (`gh api repos/.../commits/main/check-runs`) before applying, otherwise a
typo'd context name will block every merge.
