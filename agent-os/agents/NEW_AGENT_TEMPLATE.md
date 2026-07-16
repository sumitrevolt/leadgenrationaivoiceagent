# 🆕 NEW AGENT TEMPLATE — naya AI staff agent add karne ka SOP

> Council rule (2026-06-25 billionaire-audit): naya agent SIRF tab jab wo *measurable operational leverage* de jo current roster nahi deta. Pehle folding/reuse consider karo (Hermes ne Kavya/Tara ke engines REUSE kiye the).

## Checklist (sab mandatory)

1. **Roster entry:** `app/platform/team.py` STAFF me key add karo — `product` (voice/marketing/platform), `name`, `emoji`, `title`, `duties` (KPI naam ke saath), `schedule`.
2. **Feature gate:** naya env flag (e.g. `MY_AGENT=1`), INERT default, `AUTOMATION_FLAGS` registry me register.
3. **Engine module:** `app/agents/<name>.py` — padosi copy karo (lazy `from app.voice_agent import free_ai` FUNCTION ke andar, module-top pe nahi; try/except + graceful degradation; `log_event()` attribution).
4. **Scheduler wiring:** `team_scheduler.py` me job (boot-grace respect karo) — heavy kaam Celery only, web process me nahi.
5. **Spec regenerate:** `python scripts/gen_agent_os_specs.py` — agent-os/agents/<key>.md auto-banega.
6. **Test + verify:** targeted pytest + `prod_check.py` + duplicate-route grep. Evidence ke bina done nahi.
7. **Memory write-back:** `memory/decisions.md` me ADR + CLAUDE.md `## Current State`.

## Standards jo HAR agent pe lagte hai

- `agent-os/standards/global/config.md` · `global/logging.md` · `global/feature-flags.md`
- Product-specific: voice → `voice/*`; marketing → `backend/error-handling`, `backend/lazy-imports`; platform → `backend/*`
- Billing touch → `billing/billing-truth.md` (packages.py = single source)

## OmniRoute (optional, double-gated)

Agent LLM calls default free_ai chain use karte hai. OmniRoute route tabhi jab `OMNIROUTE_ENABLED=1` **aur** `OMNIROUTE_AGENTS=1` — sanitized payload only, free_ai fallback hamesha intact.
