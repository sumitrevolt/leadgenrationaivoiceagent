---
name: automation-pipeline
description: Operate LeadGen AI's end-to-end automated growth pipeline — scrape → score → email outreach → reply-triage → journeys → cadence → sales deals. Use when the user says "automation chalu/band karo", "pipeline status", "leads kyun nahi aa rahe", "outreach automate", "scheduler", "growth pipeline", or wants to enable/verify the daily AI-staff automation.
---

# Automation Pipeline (lead → revenue · free-stack · ban-safe)

Poora funnel `app/platform/team_scheduler.py` (in-process APScheduler, single-instance lock) chalata hai. Sab additive + gated + free-stack. Kuch bhi cold-blast nahi (ban-safe = drafts/1-click human send).

## Daily pipeline (IST, auto)
1. **09:30 scrape** — `prospect` job. `NICHE_ROTATION=1` → `niche_prospector.run()` (sab 42 niches round-robin, `data/niche_prospect_cursor.json`); warna 4-niche `prospector.run_prospecting()`. Auto `lead_scoring.rescore_db()`.
2. **10:30 email outreach** — `auto_outreach.run_email_outreach()` + Day-3/7 followups. Hostinger SMTP, MX-verified, cap 25/day. Gated `AUTO_EMAIL_OUTREACH=true`.
3. **hourly reply-triage** — `reply_agent.run_reply_triage()` (IMAP → free-LLM intent → draft + interested→`sales_pipeline.upsert_deal`). Gated `REPLY_AGENT=1`. Auto-send OFF.
4. **07:00 content job** — `auto_content` + `content_schedule.run_due()` + `cadence.run_due()` (gated `CADENCE_ENGINE`) + `sales_pipeline.run_pipeline()` (gated `SALES_ENGINE`).
5. **journeys** — inquiry/signup events → `journeys` drafts (gated `JOURNEY_ENGINE`).
6. **hourly** — `ops_watchdog` (gated `OPS_WATCHDOG`, email-alert) + `onboarding` sweep (gated `AUTO_ONBOARD`).

## Operate (admin)
- Status: `python scripts/setup_status.py` (flags) + `/app/team` dashboard + `GET /api/admin/live-stats`.
- Scrape now: `POST /api/growth/niche/scrape`. Hot leads: `GET /api/growth/leads/hot`; rescore: `POST /api/growth/leads/rescore`.
- Cadence: `POST /api/growth/cadence/enroll` then `/cadence/run`. Sales: `POST /api/growth/sales/run`.
- Flags safe enable → use the `automation-flags` skill.

## Gotchas
- Single-instance lock (`data/.scheduler.lock`) — multi-worker safe. `TEAM_AUTOMATION=0` = scheduler OFF.
- "Leads nahi aa rahe" = woh OUTBOUND targets hain, customers nahi. Pipeline tools/drafts deta hai; demo+close HUMAN hai (yahi asli gap).
- `WHATSAPP_AUTO_SEND` / cold-calling = ban/DLT risk → OFF rakho.

## Verify
Flag set → `up -d app` (recreate) → `printenv` in container → manual API trigger ya next scheduled run → `data/*.jsonl` (prospects/reply_drafts/deals/cadence_runs) me REAL output check karo.
