# 🗄️ Kabir — DB Reliability Engineer

> Source of truth: `app/platform/team.py` STAFF["kabir"] + `app/platform/agent_os_routing.py`. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `kabir`
- **Product:** platform
- **Schedule:** Daily 10:00 IST (gated DBRE_AGENT)
- **Feature gates:** `DBRE_AGENT` (env-flag, INERT default)
- **KPIs:** `db_reliability_score`

## Duties

Postgres query-health — slow-query patterns (pg_stat_statements), unused/bloating indexes, connection-pool pressure, DB size trend. KPI: db_reliability_score. Fills Pranav's blind spot (he owns backup/heartbeat/capacity, NOT query health). Read-only pg-catalog checks.

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/backend/api-routers.md`
- `agent-os/standards/backend/auth.md`
- `agent-os/standards/backend/error-handling.md`
- `agent-os/standards/backend/lazy-imports.md`
- `agent-os/standards/backend/pydantic-models.md`

## Routing & governance (app/platform/agent_os_routing.py)

- **Category:** `recovery_incident`
- **OmniRoute task:** `NONE (forbidden)`
- **Privacy class:** `SENSITIVE_LOCAL_ONLY`
- **OmniRoute eligible:** no (still needs `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS` + key)
- **May write production data:** no
- **May contact customers:** no
- **Human approval before publish:** no
- **Free models OK:** yes
- **Auto-run allowed:** yes
- **Max retries / timeout / queue:** 1 / 45s / `celery`
- **Notes:** DBRE — schema/ops sensitive; no OmniRoute.

Disable one agent: uska feature gate env unset karo (ya Office HQ pause) — poora system band mat karo.

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
