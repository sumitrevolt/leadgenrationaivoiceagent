# TASKS — Competitor Feature-Gap Backlog (2026-06-10)

> Source: `docs/Competitor_Top20_Feature_Gap_2026.md` (26 competitors deep research).
> Rule: build se pehle `grep '@router' app/api/*.py` — duplicates already dedupe kiye, par double-check karo.

## ✅ LAUNCH READINESS (2026-06-22) — Marketing Product-1 GO

**Verdict: code GREEN · UPI armed · first paid customer UNBLOCKED.**

- ✅ **Live activation** (`/api/activation/summary`): `ready_for_first_paid_customer=true`, `blocker_count=0`, sole WARN=`turnstile` (optional bot-protection).
- ✅ **Local prod_check**: ALL CHECKS PASSED (809 routes).
- ✅ **Launch path smoke** (`scripts/launch_path_smoke.py`): `/pricing` `/start` `/app/login` 200 · pay-info enabled · signup route · admin UPI queue mounted.
- ✅ **Payments**: Razorpay **REMOVED 2026-06-18** — primary path = **manual UPI** (`UPI_VPA` / admin configure). Stripe = international only.
- ✅ **VPS readiness flags ON**: `REVENUE_TRENDS`, `CLIENT_TIMELINE`, `SYS_HEALTH_DETAIL`, `EVAL_GATE`, `PLAN_RATE_LIMIT`, etc. (`scripts/vps_enable_readiness_flags.py`).
- ✅ **Sentry armed** on VPS (`SENTRY_DSN` set). **Turnstile still unset** — Cloudflare widget keys user-action.
- ✅ **Email enrich batch** (2026-06-22): `scripts/sales_ops_batch.py` — 30 scanned, **16 emails found** (648 with-email / 1842 phone-only remaining).

## ✅ PRODUCTION-READINESS AUDIT (2026-06-14) — superseded by 2026-06-21/22 audits

- ✅ Automation loops firing; Hermes healthy; pipeline flowing.
- ⚠️ **Flags OFF (intentional)**: CRM_SYNC, NEWSLETTER_ENGINE, WINBACK_ENGINE, CLIENT_REPORTS, BRAND_PULSE, TEAM_REPORT — flip when use-case ready.

## P0 — ✅ BUILT 2026-06-11 (LIVE)

- [x] Branded frames + daily-post feed · business card · magic resize · review→post
- [x] Voice human transfer (`CALL_TRANSFER`, gated — needs Vobiz DID + DLT)
- [x] Ask AI over call data · speed-to-lead · content approval · snapshots · lead round-robin
- [x] BONUS: WA sticker · trackable proposals · dialer leaderboard

### P0 follow-ups

- [x] DEPLOYED · voice transfer intent wired · scheduler hooks · growth_tools UI tabs
- [ ] CALL_TRANSFER ON: `flow_state["owner_phone"]` + Vobiz DID + DLT (Product-2)

## P1 — ✅ BUILT 2026-06-11 (LIVE)

- [x] GEO visibility · grid rank · listings presence · outreach A/B · service reminders · video clips · pricing compare strip

## P2 / blocked

- [x] Inbox rotation code (`OUTREACH_MAILBOXES`) — USER: 2nd domain tab ON
- [x] AI avatar video (Pollinations key)
- **EXTERNAL-BLOCKED**: Meta publish, GBP API, WA Flows approval, DLT, missed-call DID
- **SKIP FOREVER**: unofficial WA auto-responder, Justdial/IndiaMART/LinkedIn scrape

## Pipeline Review — active ops (2026-06-22)

- [ ] **USER/DAILY**: dialer sprint — `/app/dialer` se 20–30 calls/din (phone-only pool **1842** DB leads; script: `scripts/sales_ops_batch.py`)
- [x] Email-finder enrich batch — 16/30 enriched 2026-06-22; rerun `docker exec leadgen_app python scripts/sales_ops_batch.py --limit 50 --apply`
- [ ] USER: replied prospects follow-up (check `/app/outreach` + reply drafts)
- [ ] Reply intent classifier tune (re-measure after junk guard)
- [ ] Sales-team deep-dives → hot leads score 70+
- [ ] Inbound watch: /compare SEO + channel experiments (2–4 weeks)

## User-action pending (NOT code gaps)

- [ ] **Turnstile** (optional WARN): `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET_KEY` in VPS `.env`
- [ ] **First paid customer**: pricing → signup → UPI pay → admin `/api/admin/upi/activate`
- [ ] DLT via Udyam · Vobiz recharge + DID (Product-2 voice only)
- [ ] Cloudflare tunnel/WAF (optional infra)
