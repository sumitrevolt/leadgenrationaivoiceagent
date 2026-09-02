# 📣 Isha — Marketing Executive

> Source of truth: `app/platform/team.py` STAFF["isha"] + `app/platform/agent_os_routing.py`. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `isha`
- **Product:** marketing
- **Schedule:** On-demand (marketing)

## Duties

Clients ke liye AI social posts (FB/Insta captions), Google Business Profile tips, festival/offer content

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/backend/error-handling.md`
- `agent-os/standards/backend/lazy-imports.md`

## Routing & governance (app/platform/agent_os_routing.py)

- **Category:** `content_generation`
- **OmniRoute task:** `leadgen.agent_ops`
- **Privacy class:** `INTERNAL_SANITIZED`
- **OmniRoute eligible:** yes (still needs `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS` + key)
- **May write production data:** yes
- **May contact customers:** no
- **Human approval before publish:** yes
- **Free models OK:** yes
- **Auto-run allowed:** yes
- **Max retries / timeout / queue:** 2 / 45s / `celery`
- **Notes:** —

Disable one agent: uska feature gate env unset karo (ya Office HQ pause) — poora system band mat karo.

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
