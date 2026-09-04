# Coordination — 9-Bot FINAL Guide (owner-friendly, simple)

> **Ek line:** Saare AI "staff" ek hierarchy me kaam karte hain — **Boss → 8 Department
> Bots → 31 Agents**. Aur abhi LIVE sirf ₹5L sprint loop chal raha hai; baaqi blueprint.
> Ye file = FINAL answer: kaun sa bot, kaun se **agents**, kaun se **tools**, kya kaam.

## Hierarchy

```
                                  👑 BOSS (owner orchestrator)
   ┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
 Revenue/  Lead Intl.  Outreach/  Voice/    Marketing/  Eng/SRE   QA/Ana.   Admin/
 CRO        Lead Lab   Conversation Swara     Content                lytics    Finance
 (7 dept bot under boss, + QA/Finance alag = 8 department bots)
```

## THE 9 BOTS (Bot · Agents · Kya karta hai · Tools)

| # | Bot | Key agents (31 me se) | Kya karta hai | Tools (asli) |
|---|-----|----------------------|----------------|--------------|
| 1 | **👑 Boss / Owner Orchestrator** | manager | Target set karo, priority queues, conflicts solve, safety/kill-switch enforce, revenue dashboard, duplicates roko | kanban, `coordinator.coordinate()`, `scripts/leadgen_daily_brief.py` |
| 2 | **Revenue / CRO** | nikhil, rohan | Money: offers, pricing, funnel, upsell, reactivation → **collected revenue** | `ops_revenue_summary`, `/api/admin/revenue/offers/issue` (UPI pay-link), `/api/admin/promo/create`, dunning, packages |
| 3 | **Lead Intelligence** | dev, neha, kabir, diya | Lead dhoondhna, score, dedupe, qualify — kabhi fake contact nahi | prospector, scoring, `ops_hot_queue`, Postgres query-health, DB data-integrity |
| 4 | **Outreach & Conversation** | isha, zara, swara, ananya, riya, priya | WhatsApp/email follow-up, reply classify, appointment — suppression/opt-out aware | reply_agent, email engine (≤25/day), `ops_hot_queue`+`ops_hot_queue_action` (done/park), WAHA (gated), calendar |
| 5 | **Voice / Swara** | tara, lekha, meera, raksha | Call queue, scripts, qualification, call analytics, human-escalation | Vobiz/DND (fail-closed, TRAI window), call_analytics, call_transfer (gated) |
| 6 | **Marketing / Content** | ravi, anika, ira, kiran | Creatives, social posts, video, campaigns, organic inbound | SEO/GSC, social (Postiz/Meta, gated), content/Journey engines (gated) |
| 7 | **Engineering / SRE** | vikram, guru, pranav, aryan, kavya, hermes, arnav, arya | Bugs, Docker, VPS, deploy, infra, recovery, security | infra_handler (0–100 score), prod_check, deploy_vps.sh, Celery, health, pip-audit |
| 8 | **QA / Analytics** | arjun | End-to-end test, funnel analytics, regression, unsupported claims ko challenge karo | pytest, reconciliation, voice test scripts |
| 9 | **Admin / Finance** | vidya | Billing, subscription, GST invoices, unit-economics | subscription, gst_invoice (INV ledger), margin/LLM-spend checks |

## Tools bank (jo bots asli me use karte hain)

Hermes Desktop ke `leadgen` MCP server me **54 tools** registered (admin, Bearer-gated). Key:

| Tool | Kya karta hai | Kaun use karta hai |
|------|---------------|---------------------|
| `ops_hot_queue` (`GET /api/ops/hotqueue`) | Warm/intent leads ka read-only snapshot | Sales, Lead Intel |
| `ops_hot_queue_action` (`POST /api/ops/hotqueue/action`) | Hot-queue row **done/park** (idempotent, no send) | Outreach |
| `ops_revenue_summary` (`GET /api/ops/revenue-summary`) | Verified collected ₹ (GST ledger) | Revenue, Boss |
| `/api/admin/revenue/offers/issue` | Payable offer → **hosted UPI pay-link** (WhatsApp close) | Revenue/Sales close |
| `/api/admin/promo/create` · `/api/public/launch-offer` | Launch/promo code + pricing-page deadline | Revenue |
| `scripts/leadgen_daily_brief.py` | Read-only prod brief (SSH → docker → psql) | Boss + sprint bots |
| `hermes kanban swarm` | Cycle graph (workers → verifier → synthesizer) | Sprint engine |

## Live vs Blueprint

- **LIVE (abhi):** ₹5L sprint loop — `sales`/`mercury`/`operations` → `sentry` → `commander`
  (CYCLE-1, day 3/7). Ye upar ki table ke bots ko data/tasks de raha hai.
- **Blueprint (baki):** 8-dept bots ka poora staff abhi **unarmed** (30/30) — DSH runtime OFF,
  flags OFF. Ye roadmap hai, abhi active nahi.

## Rules (kabhi nahi todna)

- Compliance gates off nahi (DND fail-closed · TRAI window · consent).
- Bots **draft** banate hain, **owner bhejta hai**; **money/UPI = owner-only**.
- Kuch bhi "done" sirf evidence ke saath.
