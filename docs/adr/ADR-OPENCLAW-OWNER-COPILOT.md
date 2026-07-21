# ADR-OPENCLAW-OWNER-COPILOT — OpenClaw as Owner Copilot (not supreme controller)

**Date:** 2026-07-20
**Status:** ACCEPTED (implementation Stage A — flag OFF in prod until authorized)

## Context

Owner needs one NL command interface over 31 agents without duplicating workforce,
bypassing Owner OS, or granting OpenClaw shell/DB/billing/calling power.

## Decision

Integrate OpenClaw as an **optional edge Copilot**:

```text
Admin → OpenClaw Owner Copilot → Owner OS → Boss → 31 agents → Celery
```

- Reuse existing 31 agents + Boss; do not create 31 OpenClaw clones.
- Typed command allowlist + GREEN/AMBER/RED lanes.
- `OPENCLAW_ENABLED=0` default; fail-closed.
- AMBER parks Owner OS approval; RED always refuse.
- Calling / billing / deploy / bulk outreach never via OpenClaw.

## Consequences

- New package `app/integrations/openclaw/` + `/api/owner-copilot/*` + Owner OS UI tab.
- Core SaaS has zero hard dependency on OpenClaw.
- Stage A prod = read-only allowlist only after explicit deploy auth.

## Architecture — inbound only (locked 2026-07-20)

```text
OpenClaw Gateway (owner-copilot agent + leadgen_owner_command tool)
        │  POST /api/owner-copilot/command
        │  Authorization: Bearer OPENCLAW_API_TOKEN
        ▼
LeadGen Owner Copilot adapter
        ▼
Owner OS (sole action authority)
        ▼
existing dispatcher / 31 agents
```

- LeadGen core runtime does **not** depend on OpenClaw being up.
- `OPENCLAW_BASE_URL` is **optional callback only** (notify_gateway). Empty = no-op.
  It is **not** on the command path. Do not treat empty BASE_URL as a broken install.
- Preferred model: OpenClaw → LeadGen. Not LeadGen → OpenClaw for commands.

## Local Gateway packaging (no secrets in git)

- Plugin: `config/openclaw/plugins/leadgen-owner-copilot/` (tool `leadgen_owner_command`)
- Template: `config/openclaw/gateway.openclaw.json5` + `config/openclaw/env.local.example`
- Runtime secrets/state: `config/openclaw/.local/` (gitignored)
- Agent id: `owner-copilot` — allowlist-only tool; shell/SQL/browser/cron denied
- OpenClaw engine requires Node `>=24.15.0` (or `22.22.3+` / `25.9.0+`) for SQLite WAL safety

## Alternatives rejected

- OpenClaw as supreme orchestrator (violates Owner OS authority).
- 31 duplicate OpenClaw agents (drift + cost).
- Direct Celery/DB from OpenClaw (unsafe).
- Bidirectional mandatory coupling via `OPENCLAW_BASE_URL` (misleading; inbound-only is enough).
