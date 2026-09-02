---
name: automation-pipeline
description: Operate LeadGen AI's end-to-end automated growth pipeline — scrape → score → email outreach → reply-triage → journeys → cadence → sales deals. Use when the user says "automation chalu/band karo", "pipeline status", "leads kyun nahi aa rahe", "outreach automate", "scheduler", "growth pipeline", or wants to enable/verify the daily AI-staff automation.
---

# Automation Pipeline (lead → revenue · free-stack · ban-safe)

Poora funnel daily jobs pe chalta hai. Sab additive + gated + free-stack. Kuch bhi cold-blast nahi (ban-safe = drafts/1-click human send).

**Scheduler reality**: PRIMARY/LIVE = **Celery durable** (`leadgen_worker` concurrency=4 + `leadgen_scheduler` beat, `RUN_IN_PROCESS_SCHEDULER=0`, DLQ → Redis `dlq:failed_tasks`). In-process APScheduler (`app/platform/team_scheduler.py`, single-instance `.lock`) = **ROLLBACK** path only (`RUN_IN_PROCESS_SCHEDULER=1`+`WEB_CONCURRENCY=1`). Job logic dono me same (`_run_job_inner`); web process KABHI heavy job na chalaye.

## Daily pipeline (IST, auto)
1. **09:30 scrape** — `prospect` job. `NICHE_ROTATION=1` → `niche_prospector.run()` (sab 39 builtin niches round-robin, `data/niche_prospect_cursor.json`); warna 4-niche `prospector.run_prospecting()`. Auto `lead_scoring.rescore_db()`.
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
- `TEAM_AUTOMATION=0` = scheduler OFF. Celery path = durable (worker crash pe task survive); APScheduler path = single-instance `data/.scheduler.lock` (web restart pe re-run risk → isliye Celery primary).
- Worker recreate ke baad `redis-cli llen celery` check; >500 = `del celery` (tasks transient, beat re-schedule kar dega).
- "Leads nahi aa rahe" = woh OUTBOUND targets hain, customers nahi. Pipeline tools/drafts deta hai; demo+close HUMAN hai (yahi asli gap).
- `WHATSAPP_AUTO_SEND` / cold-calling = ban/DLT risk → OFF rakho.

## Verify
Flag set → `docker compose -f docker-compose.vps.yml up -d --no-deps app` (recreate = env reload) → `docker exec leadgen_app printenv <FLAG>` → manual API trigger ya next scheduled run → `data/*.jsonl` (prospects/reply_drafts/deals/cadence_runs) me REAL output check karo. Flags live registry: `GET /api/growth/infra/flags`.

## Enterprise gate

- **Operating loop**: Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Flag-flip ka safe procedure = `automation-flags`; naya stage/job wiring = `scheduler-job`.
- **Risk-tier: High** (outbound + billing-adjacent funnel) — galat flip = number-ban / spam / duplicate bill. Locks: ban-safe default (drafts/1-click, no cold-blast), per-stage flag, compliance fail-CLOSED.
- **Idempotency/dedupe** (pipeline bills + emails + CRM-writes): outreach cap 25/day + MX-verify + warmup ramp; followup Day-3/7 dedupe so ek lead ko repeat na jaye; `meter_call_completion`/`apply_qualified_downstream` idempotent (cross-path parity). Duplicate send = deliverability/ban hit.
- **Reliability**: jobs Celery durable (worker crash pe task survive) + DLQ `dlq:failed_tasks`; har job never-raise (ek fail = baaki chalein). Worker recreate ke baad `redis-cli llen celery` (>500 = `del celery`).
- **Compliance (fail-CLOSED)**: `WHATSAPP_AUTO_SEND`/cold-calling OFF (ban/DLT ₹10L) · email = MX-verified + bounce auto-pause · reply auto-send OFF · any voice path = TRAI 9am–7pm + DND + AI-disclosure (telephony skills). Bypass KABHI nahi.
- **Rollback (NAMED)**: stage flag OFF (`AUTO_EMAIL_OUTREACH`/`REPLY_AGENT`/etc.) + app recreate · `TEAM_AUTOMATION=0` = whole scheduler OFF · full rollback = `RUN_IN_PROCESS_SCHEDULER=1`+`WEB_CONCURRENCY=1`.
- **Evidence (done)**: `.venv\Scripts\python.exe scripts\prod_check.py` PASS + `scripts\cross_path_audit.py` (qualify/meter parity) + `GET /api/growth/infra/flags` desired state + real `data/*.jsonl` output post-run.
