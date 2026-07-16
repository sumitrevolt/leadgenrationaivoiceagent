# 🆕 NEW AGENT TEMPLATE — naya AI staff agent add karne ka SOP

> Council rule (2026-06-25 billionaire-audit): naya agent SIRF tab jab wo *measurable operational leverage* de jo current roster nahi deta. Pehle folding/reuse consider karo (Hermes ne Kavya/Tara ke engines REUSE kiye the).

## Checklist (sab mandatory)

1. **Roster entry:** `app/platform/team.py` STAFF me key add karo — `product` (voice/marketing/platform), `name`, `emoji`, `title`, `duties` (KPI naam ke saath), `schedule`.
2. **Feature gate:** naya env flag (e.g. `MY_AGENT=1`), INERT default, `AUTOMATION_FLAGS` registry me register.
3. **Routing policy:** `app/platform/agent_os_routing.py` me `_AGENT_OVERRIDES` entry — category, OmniRoute task (ya NONE), privacy class, contact/publish/write flags, retries/timeout/queue.
4. **Engine module:** `app/agents/<name>.py` — padosi copy karo (lazy `from app.voice_agent import free_ai` FUNCTION ke andar, module-top pe nahi; try/except + graceful degradation; `log_event()` attribution).
5. **Scheduler wiring:** `team_scheduler.py` me job (boot-grace respect karo) — heavy kaam Celery only, web process me nahi.
6. **Spec regenerate:** `python scripts/gen_agent_os_specs.py` — agent-os/agents/<key>.md auto-banega (routing block included).
7. **Test + verify:** targeted pytest + `prod_check.py` + duplicate-route grep. Evidence ke bina done nahi.
8. **Memory write-back:** `memory/decisions.md` me ADR + CLAUDE.md `## Current State`.

## Required template fields (fill before merge)

| Field | Example |
| --- | --- |
| Agent ID | `zara` |
| Display name | Zara |
| Business purpose | Approved social queue drain |
| Owner | Founder / ops |
| Inputs | Approved content job |
| Outputs | Published post / fail record |
| Required tools | Postiz / Telegram |
| Primary model class | free_ai bulk / OmniRoute `leadgen.agent_ops` if eligible |
| Fallback model class | free_ai chain |
| Privacy classification | INTERNAL_SANITIZED |
| Maximum runtime | 45s |
| Maximum retries | 2 |
| Cost ceiling | free-stack only |
| Queue | celery |
| Schedule | queue-driven |
| Approval gate | yes before publish |
| Success metric | post_id non-empty |
| Health check | SOCIAL_ENGINE + queue depth |
| Disable switch | `SOCIAL_ENGINE=0` / Office pause |
| Rollback | unset gate; restore prior job status |

## Standards jo HAR agent pe lagte hai

- `agent-os/standards/global/config.md` · `global/logging.md` · `global/feature-flags.md`
- Product-specific: voice → `voice/*`; marketing → `backend/error-handling`, `backend/lazy-imports`; platform → `backend/*`
- Billing touch → `billing/billing-truth.md` (packages.py = single source)

## OmniRoute (optional, double-gated)

Agent LLM calls default free_ai chain use karte hai. OmniRoute route tabhi jab:
1. Policy me `omniroute_task` set hai **aur** privacy `INTERNAL_SANITIZED`
2. `OMNIROUTE_ENABLED=1` **aur** `OMNIROUTE_AGENTS=1` **aur** `OMNIROUTE_API_KEY` set
3. Payload sanitized (`mask_customer_data` + `validate_no_secrets`)

Voice/realtime, billing, compliance, CRM-PII agents = `omniroute_task=None` (forbidden).
Fail-open: OmniRoute down = free_ai chain unchanged.
