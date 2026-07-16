# 🛰️ Hermes — Infrastructure Handler

> Source of truth: `app/platform/team.py` STAFF["hermes"] + `app/platform/agent_os_routing.py`. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `hermes`
- **Product:** platform
- **Schedule:** Har ghante (watchdog, gated INFRA_HANDLER) + pulse rotation
- **Feature gates:** `INFRA_HANDLER` (env-flag, INERT default)

## Duties

Poore infra ka scan — app readiness (db+redis), disk/memory, dead-man jobs, queue backlog, LLM chain, backup freshness → 0-100 score + Hinglish fix-actions; critical pe email alert (Kavya/Tara ke engines REUSE — aggregator/diagnoser)

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/backend/api-routers.md`
- `agent-os/standards/backend/auth.md`
- `agent-os/standards/backend/error-handling.md`
- `agent-os/standards/backend/lazy-imports.md`
- `agent-os/standards/backend/pydantic-models.md`
- `agent-os/standards/frontend/admin-actions.md`

## Routing & governance (app/platform/agent_os_routing.py)

- **Category:** `recovery_incident`
- **OmniRoute task:** `leadgen.repo_analysis`
- **Privacy class:** `INTERNAL_SANITIZED`
- **OmniRoute eligible:** yes (still needs `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS` + key)
- **May write production data:** no
- **May contact customers:** no
- **Human approval before publish:** no
- **Free models OK:** yes
- **Auto-run allowed:** yes
- **Max retries / timeout / queue:** 2 / 45s / `celery`
- **Notes:** Infra watchdog; repo_analysis route if OmniRoute agents enabled.

Disable one agent: uska feature gate env unset karo (ya Office HQ pause) — poora system band mat karo.

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
