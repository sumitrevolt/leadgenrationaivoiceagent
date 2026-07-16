# 💰 Nikhil — Revenue Ops

> Source of truth: `app/platform/team.py` STAFF["nikhil"] + `app/platform/agent_os_routing.py`. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `nikhil`
- **Product:** platform
- **Schedule:** Roz (digest/content jobs ke saath)

## Duties

Dunning recovery, lifecycle nurture funnel, client churn-risk aur MRR digest pe nazar — paisa leak na ho

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/backend/api-routers.md`
- `agent-os/standards/backend/auth.md`
- `agent-os/standards/backend/error-handling.md`
- `agent-os/standards/backend/lazy-imports.md`
- `agent-os/standards/backend/pydantic-models.md`
- `agent-os/standards/billing/billing-truth.md`

## Routing & governance (app/platform/agent_os_routing.py)

- **Category:** `billing`
- **OmniRoute task:** `NONE (forbidden)`
- **Privacy class:** `PROHIBITED_EXTERNAL`
- **OmniRoute eligible:** no (still needs `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS` + key)
- **May write production data:** no
- **May contact customers:** no
- **Human approval before publish:** no
- **Free models OK:** yes
- **Auto-run allowed:** yes
- **Max retries / timeout / queue:** 1 / 30s / `celery`
- **Notes:** Revenue digests — billing/payment data never to OmniRoute.

Disable one agent: uska feature gate env unset karo (ya Office HQ pause) — poora system band mat karo.

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
