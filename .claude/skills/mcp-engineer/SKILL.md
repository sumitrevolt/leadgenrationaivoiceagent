---
name: mcp-engineer
description: Anything MCP — /mcp endpoint, MCP-as-product /api/mcp-product/v1/*, A2A Agent Card, mcp_keys, Arya staff agent, MCP auth/key-rotation/quota debugging.
---

# mcp-engineer (skill)

**Use when**: anything MCP — `/mcp` endpoint, MCP-as-product (`/api/mcp-product/v1/*`), A2A Agent Card, mcp_keys, Arya VPS staff agent, Claude Desktop MCP config for leadsgenai.in, MCP auth failures / key rotation / quota debugging, adding a new MCP capability.

**Do NOT use for**: voice agent, telephony, billing, marketing, council, or unrelated code. Hand back to general agent if cross-cutting.

## Quick mental model (council 2026-06-26)

Project me 3 MCP layers:

| Layer | Path | Gate | Audience |
|-------|------|------|----------|
| Expose | `/mcp` (fastapi-mcp) | `FASTAPI_MCP_TOKEN` OR `MCP_IP_ALLOWLIST` | Claude Desktop (admin tools) |
| Product | `/api/mcp-product/v1/*` | `MCP_PRODUCT=1` + `X-LeadGen-Key` | B2B customers (metered) |
| A2A Card | `/.well-known/agent.json` | public | cross-agent discovery |

Plus `Arya` staff agent (`app/platform/mcp_engineer.py`) = hourly health pulse + key rotation watch + auth-failure detection + ntfy alerts.

## When invoked

1. **Identify which layer** the user is asking about. If they say "MCP not working" without specifics, run `audit_mcp_security()` first:
   ```python
   from app.platform import mcp_engineer
   print(mcp_engineer.audit_mcp_security())
   ```
2. **Spawn the `mcp-engineer` Claude subagent** (`.claude/agents/mcp-engineer/AGENT.md`) for any code change — it has the right scope rules and tools whitelist.
3. **For pure debugging** (no code change), use the smoke commands listed in the AGENT.md.

## Activation checklist (for first-time setup)

VPS `.env`:
```
MCP_PRODUCT=1
MCP_ENGINEER=1
FASTAPI_MCP_TOKEN=<random 32+ chars>      # OR
MCP_IP_ALLOWLIST=72.61.245.204,1.2.3.4    # CSV of admin IPs
# Optional tunables:
MCP_KEY_ROTATION_DAYS=90
MCP_QUOTA_PRESSURE_PCT=80
MCP_AUTH_FAIL_ALERT=20
```

Claude Desktop `claude_desktop_config.json` (local user's machine):
```json
{
  "mcpServers": {
    "leadsgenai": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch", "https://leadsgenai.in/mcp/"],
      "env": { "FASTAPI_MCP_TOKEN": "<paste-token-from-vps-env>" }
    }
  }
}
```

After both: `docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app worker scheduler`, then verify:
- `curl -s https://leadsgenai.in/.well-known/agent.json | jq` → returns A2A card
- `curl -s https://leadsgenai.in/api/mcp-product/v1/discover | jq` → `"enabled": true`
- `curl -sI https://leadsgenai.in/mcp/` → `401` or `403` (NOT 200)
- `/app/team` page → Arya appears in platform staff list with hourly mcp_pulse events

## Test command

```bash
pytest tests/test_mcp_engineer.py -v
```

## File map (single source of truth)

| File | Purpose |
|------|---------|
| `app/platform/mcp_engineer.py` | Arya engine (probes + score + ntfy) |
| `app/platform/mcp_keys.py` | Key issuance + auth + metering |
| `app/api/mcp_product.py` | Metered routes + A2A card |
| `app/main.py` (lines 774-791) | `/mcp` mount (must be gated) |
| `app/platform/team.py` | STAFF dict (arya entry) + team_pulse monitor |
| `app/platform/team_scheduler.py` | mcp_engineer job dispatch |
| `app/tasks/staff_jobs.py` | STAFF_JOBS tuple includes mcp_engineer |
| `app/worker.py` | Celery beat entry `staff-mcp-engineer-hourly` |
| `.env.example` | MCP_PRODUCT, MCP_ENGINEER, FASTAPI_MCP_TOKEN, MCP_IP_ALLOWLIST |
| `tests/test_mcp_engineer.py` | Unit + integration tests |

## Enterprise gate (MCP surface = exposed attack surface)

Run the operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Any MCP-surface change = **High-risk** (it's an auth boundary + metered B2B product): `duplicate-route-guard` grep before adding a route, flag-gate, named rollback, self+security review.

- **Auth fail-CLOSED:** `/mcp` mount (`app/main.py` ~774-791) MUST refuse to mount in prod without `FASTAPI_MCP_TOKEN` OR `MCP_IP_ALLOWLIST` — never expose un-gated. `/api/mcp-product/v1/*` requires `MCP_PRODUCT=1` + valid `X-LeadGen-Key`. Smoke proof: `curl -sI https://leadsgenai.in/mcp/` → **401/403, NOT 200**. A2A card `/.well-known/agent.json` is the ONLY public layer — keep it metadata-only (no secrets, no privileged data).
- **Metered quota:** product keys via `mcp_keys.py` — per-key quota + metering enforced server-side (no client trust); quota-exhaust = clean 429, not silent over-serve. New capability = additive route under existing prefix, never a second `/mcp` mount.
- **Key rotation + secrets:** keys live in runtime store / `.env` only (never committed); `MCP_KEY_ROTATION_DAYS=90` watched by Arya. Rotating/issuing a key = no-restart admin path; `scripts/check_secrets.py` clean.
- **Observability:** Arya (`mcp_engineer.py`, hourly `MCP_ENGINEER=1`) = health score + quota-pressure (`MCP_QUOTA_PRESSURE_PCT`) + auth-failure burst (`MCP_AUTH_FAIL_ALERT`) → ntfy. Events on `/app/team` (arya `mcp_pulse`). Diagnose-first: `mcp_engineer.audit_mcp_security()`.
- **Reliability:** Arya pulse via Celery beat `staff-mcp-engineer-hourly` — never-raise, isolated; registered in `team_scheduler` + `staff_jobs.STAFF_JOBS` + `automation_health` parity (dead-man).
- **Rollback (NAMED):** flag OFF (`MCP_PRODUCT=0` / `MCP_ENGINEER=0` / unset token = mount refuses = surface dark) · revoke the issued key · container recreate `docker compose -f docker-compose.vps.yml build app && up -d --no-deps app worker scheduler`.
- **Evidence (done):** `pytest tests/test_mcp_engineer.py -v` green + `scripts/prod_check.py` + the 4 smoke curls above (agent.json ✓, discover `enabled:true`, `/mcp/` 401/403, Arya in `/app/team`). Scope discipline: stay inside MCP files — no voice/billing/marketing edits. Live deploy = explicit user-auth.
