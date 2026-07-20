# OpenClaw Owner Copilot

Owner Copilot + Chief of Staff edge layer for LeadGen AI.

## Verdict (2026-07-20)

```text
Local real-gateway integration verified; review-ready; production rollout pending explicit authorization.
```

- Production not deployed.
- Production flag remains OFF (`OPENCLAW_ENABLED=0` default).
- Stage B Boss multi-agent mission orchestration is **not** included.
- Prometheus counters are **not** included.

## Hierarchy (locked)

```text
Sumit / Admin
      ↓
OpenClaw Owner Copilot   ← this integration (optional)
      ↓
Owner OS                 ← sole action authority
      ↓
Boss / Manager
      ↓
31 existing agents
      ↓
Celery / workflows / delivery
```

OpenClaw does **not** replace Owner OS, Boss, Celery, or the 31 agents.
Disabling `OPENCLAW_ENABLED=0` must not stop any core SaaS path.

## Architecture — inbound only

```text
OpenClaw Gateway (agent id: owner-copilot)
  → tool leadgen_owner_command
  → POST http://127.0.0.1:<leadgen>/api/owner-copilot/command
  → Authorization: Bearer OPENCLAW_API_TOKEN
  → Owner Copilot adapter → Owner OS → existing dispatcher
```

- LeadGen does **not** depend on OpenClaw for core runtime.
- `OPENCLAW_BASE_URL` is **optional callback only** (`notify_gateway`). Empty = no-op.
  It is **not** on the command path.

## Local Gateway packaging (no secrets in git)

| Path | Purpose |
|------|---------|
| `config/openclaw/plugins/leadgen-owner-copilot/` | OpenClaw tool plugin |
| `config/openclaw/gateway.openclaw.json5` | Template (placeholders) |
| `config/openclaw/env.local.example` | Env template |
| `config/openclaw/owner-copilot.md` | Persona instructions |
| `config/openclaw/.local/` | **gitignored** runtime tokens + state |

### Local setup

1. Node `>=24.15.0` (OpenClaw SQLite WAL requirement).
2. `npm install openclaw@2026.7.1-2` (or current) into a local dir (e.g. `C:\oc`).
3. Copy `env.local.example` → `config/openclaw/.local/env.local` and set tokens.
4. Copy template into `.local/openclaw.json` (plugin path absolute; gateway auth token).
5. Start LeadGen with `OPENCLAW_ENABLED=1` + matching `OPENCLAW_API_TOKEN` (defaults stay OFF in `.env.example`).
6. Start gateway:
   ```text
   OPENCLAW_CONFIG_PATH=.../.local/openclaw.json
   OPENCLAW_STATE_DIR=.../.local/state
   node openclaw.mjs gateway --port 18789 --bind loopback --auth token --token <gateway-token>
   ```
7. Prove via `POST http://127.0.0.1:18789/tools/invoke` tool `leadgen_owner_command`.

### Trust boundary

- Agent allowlist: only `leadgen_owner_command`
- Denied: `exec`, `spawn`, `shell`, `fs_write`, `browser`, `cron`, `gateway`, …
- No VPS credentials, no DB, no Celery direct, no production secrets in plugin

## Safety lanes

- **GREEN** — autonomous after auth (read-only Stage A)
- **AMBER** — Owner OS approval required (`OPENCLAW_REQUIRE_APPROVAL_FOR_AMBER=1`)
- **RED** — always refused via OpenClaw (plugin allowlist + LeadGen lanes)

## Typed commands (Stage A default allowlist)

`platform.status`, `agents.list`, `agent.status`, `approvals.list`, `delivery.status`, `queues.status`, `business.daily_summary`, `owner.next_actions`

Local AMBER proof may add `agent.pause` (parks approval; no silent mutate).

## Auth

- Admin JWT (browser) **or** `OPENCLAW_API_TOKEN` gateway bearer
- Rate limit: `owner_copilot` / `owner_copilot_nl` buckets

## API

- `GET  /api/owner-copilot/status` — works even when disabled (shows flag)
- `POST /api/owner-copilot/command` — typed command
- `POST /api/owner-copilot/nl` — NL → typed proposal / execute
- `GET  /api/owner-copilot/daily-brief`
- `GET  /api/owner-copilot/approvals`
- `GET  /api/owner-copilot/catalogue`
- `GET  /api/owner-copilot/commands/{id}`

## UI

Owner OS → **Owner Copilot** tab (`/app/owner`).

## Rollback

```text
OPENCLAW_ENABLED=0
```

Immediate. No recreate required for core services. OpenClaw Gateway stop does not affect LeadGen.
