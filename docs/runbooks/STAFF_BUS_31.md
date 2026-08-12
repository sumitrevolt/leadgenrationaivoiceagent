# STAFF Bus (31-agent) — runbook

**Flag:** `STAFF_BUS_ENABLED` (default OFF / inert)
**Rollback:** set `STAFF_BUS_ENABLED=0` (or unset). No production side-effects when OFF.
**Module:** `app/platform/staff_bus/`

## What this is / is not

- **Is:** Buzz-facing collaboration bus for the canonical **31 STAFF** workforce (`team.STAFF` → Boss + 7 teams → 30 workers).
- **Is not:** production executor, second control plane, or Comb-as-STAFF (#32). Celery + Owner OS remain execution authority.
- **Identity:** one signed bridge projection (`STAFF_BUS_HMAC_SECRET`), not 31 Desktop keypairs.

## Commands

```bat
.venv\Scripts\python.exe -m pytest tests/test_staff_bus_2026_08_12.py -q
.venv\Scripts\python.exe scripts/staff_bus_canary.py --out docs/evidence/staff_bus_canary_latest.json
```

## Security gates (fail-closed)

- Unknown / malformed event types → DLQ
- Duplicate idempotency keys → refuse
- Unknown source agent → refuse
- Rate limit on live publishers (`STAFF_BUS_RATE_LIMIT_PER_MIN`, default 600)
- Kill switch: `STAFF_BUS_ENABLED=0`
- Synthetic canaries use tenants `bus_setup-*` only; zero customer outbound

## Boss + Second Brain

Decision-bearing canaries reuse `app.platform.boss_decision_governance`:
propose → Second Brain advice → Boss review → approve **or** `agent_unarmed` refuse for held/disabled rollout (governed GO).

## Control-plane Buzz agents (not STAFF count)

Boss / Fizz / Honey / Bumble / Comb — Desktop ACP harnesses. Comb = read-only reviewer infra. Correlated canaries require resolved `--mention` + `messages get --since`.

## Hosted vs local relay

- Hosted primary: `https://leadsgenai.communities.buzz.xyz`
- Local DR/dev: `ws://127.0.0.1:3100` (not silent prod replacement)
- Stale `:3000` refs are ops aliases only

## Evidence

See `docs/evidence/staff_bus_canary_*.json` for the 31-row synthetic evidence table.
