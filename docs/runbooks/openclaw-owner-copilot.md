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

## Authorization model

| Actor | Path | Requirement |
|-------|------|-------------|
| Human / browser | JWT | Canonical **super-admin** only (`UserRole.SUPER_ADMIN`). Normal admin / module-RBAC → 403 |
| OpenClaw Gateway | Bearer `OPENCLAW_API_TOKEN` | Constant-time token match **and** socket peer in `OPENCLAW_GATEWAY_ALLOWED_IPS` |

`X-Forwarded-For` is **not** trusted for Gateway machine auth (spoof-resistant). Use same-host loopback or an explicitly documented private Docker/network peer IP.

## Gateway token operational rules (mandatory)

- Cryptographically random token, **≥ 256 bits** entropy (e.g. `openssl rand -hex 32`)
- Separate from admin JWTs and all other platform secrets
- Stored only in environment / secret manager — never in git, URLs, logs, screenshots, PR bodies, or command output
- Rotate before initial production Stage A rollout
- Rotate immediately after suspected exposure
- Gateway and LeadGen receive the **same** token via separate secure configuration
- Gateway process runs as an **unprivileged** system user
- Gateway has **no** Docker socket, root SSH, raw database, or `.env` directory access
- Gateway binds **loopback only** — never expose Gateway publicly

## Network boundary (production design)

```text
OpenClaw Gateway (loopback / private)
  → LeadGen internal application port (container :8080 / host loopback)
  → peer IP must be in OPENCLAW_GATEWAY_ALLOWED_IPS
```

Safe default:

```bash
OPENCLAW_GATEWAY_ALLOWED_IPS=127.0.0.1,::1
```

If reverse proxy / Docker makes the app see only a container gateway IP, allowlist **that exact private IP** (document it). Do not use broad CIDRs unless strictly required and documented. Empty allowlist = fail closed for token-only auth.

## Local enable (dev only)

```bash
# process env / .env.local — NOT committed defaults
OPENCLAW_ENABLED=1
OPENCLAW_ALLOW_RED_ACTIONS=0
OPENCLAW_API_TOKEN=<local-dev-token-min-32-bytes-hex>
OPENCLAW_GATEWAY_ALLOWED_IPS=127.0.0.1,::1
OPENCLAW_ALLOWED_COMMANDS=platform.status,agents.list,agent.status,approvals.list,delivery.status,queues.status,business.daily_summary,owner.next_actions,runtime.status,agents.unhealthy,automation.status,automation.agents
```

`.env.example` stays `OPENCLAW_ENABLED=0`.

Local AMBER proof (non-production only) may temporarily add `agent.pause` — parks Owner OS approval; no silent mutate. Production strips AMBER until Stage B durable idempotency.

### Real Gateway proof (local)

```bash
# After Node >=24.15 + openclaw install + config/openclaw/.local/*
curl -sS http://127.0.0.1:18789/tools/invoke \
  -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool":"leadgen_owner_command","args":{"command":"agents.list","idempotency_key":"proof-1"},"agentId":"owner-copilot"}'
```

Expect: HTTP 200, agents count = 31, calling HARD OFF.

- `delivery.status` without `tenant_id` → controlled `FAILED` / `tenant_id required` (never defaults to Jiya)
- Valid token from untrusted source IP → LeadGen `403`
- RED (`calling.enable`, `shell.execute`, …) → rejected

## Browser smoke

1. Open `/app/owner` → tab **Owner Copilot**
2. Authenticate as **super-admin** JWT (normal admin → 403)
3. Confirm flag badge, Calling HARD OFF, agents=31 context
4. Parse/Preview GREEN; Run shows SUCCEEDED + correlation id
5. Typed RED proven via Gateway `/tools/invoke`

## Prod Stage A (read-only GREEN only)

Only after tests + owner authorization to deploy:

```text
OPENCLAW_ENABLED=1
OPENCLAW_ALLOWED_COMMANDS=<GREEN list only>
OPENCLAW_ALLOW_RED_ACTIONS=0
OPENCLAW_GATEWAY_ALLOWED_IPS=127.0.0.1,::1   # or exact private peer
OPENCLAW_API_TOKEN=<rotated-256-bit-secret>
```

Structural guard: production AMBER entries are stripped when durable Redis idempotency is unavailable. In-process idempotency cache is a GREEN-read optimization / local tests only — **not** AMBER production readiness.

No production deploy without explicit authorization.

## Stage B follow-up (not claimed ready)

- Durable Redis `OpenClawIdempotencyStore` for AMBER mutations across workers
- Explicit Stage B enablement after durable store proven
- Boss multi-agent missions / Prometheus — still out of scope

## Incident

| Symptom | Action |
|---------|--------|
| Unexpected mutations | `OPENCLAW_ENABLED=0` + check Owner OS audit `openclaw.*` |
| 503 on /command | Expected when flag off |
| 403 human | Expected for non-super-admin |
| 403 gateway | Token OK but source IP not allowlisted (or allowlist empty) |
| RED refused | Correct — use admin workflows |
| Calling enabled via Copilot | Impossible by design — verify `PLATFORM_DIAL_DAILY=0` |
| Gateway down | LeadGen/Owner OS continue; Copilot machine path unavailable |

## Verify calling still HARD OFF

```bash
# Owner OS kill board / platform_dial.enabled == false
# Prod /health only when authorized to probe
```
