# Runbook — OpenClaw Owner Copilot

## Disable (immediate)

```bash
# VPS /opt/leadgen .env
OPENCLAW_ENABLED=0
# recreate app only if env already loaded into container:
# APP_VERSION=<sha> docker compose -f docker-compose.vps.yml up -d app --force-recreate
```

Core agents, Owner OS, Celery, billing, customer portal — unaffected.
Stopping the OpenClaw Gateway process alone is also safe — LeadGen stays healthy.

## Local enable (dev only)

```bash
# process env / .env.local — NOT committed defaults
OPENCLAW_ENABLED=1
OPENCLAW_ALLOW_RED_ACTIONS=0
OPENCLAW_API_TOKEN=<local-dev-token>
OPENCLAW_ALLOWED_COMMANDS=platform.status,agents.list,agent.status,approvals.list,delivery.status,queues.status,business.daily_summary,owner.next_actions,agent.pause
```

`.env.example` stays `OPENCLAW_ENABLED=0`.

### Real Gateway proof (local)

```bash
# After Node >=24.15 + openclaw install + config/openclaw/.local/*
curl -sS http://127.0.0.1:18789/tools/invoke \
  -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool":"leadgen_owner_command","args":{"command":"agents.list","idempotency_key":"proof-1"},"agentId":"owner-copilot"}'
```

Expect: HTTP 200, agents count = 31, calling HARD OFF.

AMBER (`agent.pause` confirm=false) → `APPROVAL_REQUIRED` (no silent mutate).
RED (`calling.enable`, `shell.execute`, …) → rejected by plugin allowlist and/or LeadGen RED lane.

## Browser smoke

1. Open `/app/owner` → tab **Owner Copilot**
2. Authenticate (admin JWT) or local gateway bearer for Copilot API
3. Confirm flag badge, Calling HARD OFF, agents=31 context
4. Parse/Preview GREEN; Run shows SUCCEEDED + correlation id
5. Typed AMBER/RED proven via Gateway `/tools/invoke` (NL fail-safe may map ambiguous text to read-only)

## Prod Stage A (read-only)

Only after tests + owner authorization to deploy:

```text
OPENCLAW_ENABLED=1
OPENCLAW_ALLOWED_COMMANDS=<GREEN list>
OPENCLAW_ALLOW_RED_ACTIONS=0
```

No AMBER mutations until Stage A proven. No production deploy in the local-closure PR.

## Incident

| Symptom | Action |
|---------|--------|
| Unexpected mutations | `OPENCLAW_ENABLED=0` + check Owner OS audit `openclaw.*` |
| 503 on /command | Expected when flag off |
| RED refused | Correct — use admin workflows |
| Calling enabled via Copilot | Impossible by design — verify `PLATFORM_DIAL_DAILY=0` |
| Gateway down | LeadGen/Owner OS continue; Copilot machine path unavailable |

## Verify calling still HARD OFF

```bash
# Owner OS kill board / platform_dial.enabled == false
# Prod /health only when authorized to probe
```
