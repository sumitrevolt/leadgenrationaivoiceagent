# REVENUE BLOCKER AUDIT — 2026-08-15

**Auditor:** Buffy (DeepSeek Harness Master Prompt)  
**Prod SHA:** `91958c23` (DIRECT_HOST_VERIFIED 2026-08-15 06:27Z)  
**Uptime:** 8h 43m  
**MRR:** ₹1,999 (1 customer: jiya-makeover)  
**Date:** 2026-08-15  

---

## 1. EXECUTIVE VERDICT

```
REVENUE STATUS:       1 paying customer (₹1,999 MRR). ₹0 today. Funnel exists but TOP-OF-FUNNEL IS EMPTY.
AUTOMATION STATUS:    Code is production-grade. Most automations INERT or starved of input. No automated revenue loop exists end-to-end.
PRODUCTION STATUS:    Healthy (91958c23, 5/5 containers pinned, zero skew). Infra sound.
BIGGEST BLOCKER:      No lead generation pipeline is feeding prospects into the system. Autopilot has 25 hand-upserted prospects. Prospect store is effectively idle.
FIRST MONEY-PATH FAILURE: Traffic → Lead (step 1 of 12) — the funnel starts with ZERO automated inbound leads.
```

---

## 2. TOP 10 REVENUE-BLOCKING MISTAKES

### Rank 1 — P0: ZERO Automated Lead Ingestion Pipeline

**Severity:** P0 — directly blocks collecting revenue  
**Mistake:** No automated system feeds new leads into the prospect store. The 25 prospects in the sales autopilot store were **manually upserted** on 2026-08-03 (`CURRENT_STATE.md` line 187). The prospector (`app/platform/prospector.py`) exists but is NOT scheduled to run automatically — it's a manual trigger only.  
**Evidence:** `data/sales_autopilot/` — store has only hand-upserted records. No cron/scheduler entry for `prospector.run()` in `team_scheduler.py`. The scheduler `sales_autopilot` job (hourly :25) calls `run_tick()` which processes existing prospects but does NOT fetch new ones. Refill (`refill.py`) needs `SALES_AUTOPILOT_REFILL=1` + a Google Maps API key + manual trigger OR scheduled invocation — neither exists.  
**Revenue impact:** Without new leads, the entire downstream funnel (outreach → reply → hot queue → offer → payment) has NOTHING to work on. This is the single largest revenue blocker.  
**Root cause:** Prospector was designed as on-demand tool, never wired to a scheduler. Refill is flag-gated but no scheduler job invokes it.  
**Exact failure point:** `app/platform/team_scheduler.py` — no `prospector` or `refill` job registered. `app/platform/sales_autopilot/refill.py` line 19: `_FLAG = "SALES_AUTOPILOT_REFILL"` — flag is ON in prod but nothing calls `refill.run()` automatically.  
**What should happen:** Prospector runs daily (or on inquiry), finds leads in target niches/cities, upserts into autopilot store, outreach engine picks them up.  
**What actually happens:** Store is manually populated → outreach fires once on those 25 → they get emailed → store goes idle → no new prospects arrive → autopilot ticks but processes 0 items.  
**Fix:** Wire `refill.run()` into the scheduler as a daily job (e.g., `staff-prospector-refill` 10:00 IST). OR wire `prospector.run()` as a scheduled job that scrapes + enriches + ingests.  
**Files:** `app/platform/team_scheduler.py`, `app/platform/sales_autopilot/refill.py`, `app/platform/prospector.py`, `app/tasks/staff_jobs.py`  
**Validation test:** After fix, `data/sales_autopilot/prospects.jsonl` grows daily without manual intervention. Scheduler log shows `refill` or `prospector` job completing.  
**Estimated revenue path unlocked:** This single fix transforms the system from "waiting for owner to add prospects" to "prospect pipeline runs daily." Unlocks the ENTIRE downstream funnel.

---

### Rank 2 — P0: Email Outreach Per-RUN Cap = Per-DAY Cap (25 Emails/Run)

**Severity:** P0 — throttles outreach to trickle  
**Mistake:** `outreach_daily_cap=25` in `auto_outreach.py` is per-RUN, not per-DAY. The scheduler runs hourly 9:00-19:05. BUT the cap counter resets per run, meaning each hourly run could send 25 emails = ~300/day theoretical max. HOWEVER, `EMAIL_WARMUP=1` is active and the warmup ramp is **PAUSED** because complaint rate hit 0.449% (≥0.25% threshold). Evidence: `SESSION_LOG.md` line 1718 — "warmup remains PAUSED by complaint rate."  
**Evidence:** `app/platform/auto_outreach.py` — `_DAILY_CAP` check. `SESSION_LOG.md` line 327: "Email warmup recommended." `LAUNCH_READINESS_2026-08-01.md` line 18: "AUTO_EMAIL_OUTREACH 25/day is per-RUN (~275/day if hourly)." The warmup pause means the system is effectively sending 0 emails despite being "LIVE."  
**Revenue impact:** Cold email outreach — the primary automated outbound channel — is effectively DISABLED by warmup pause. The 2026-08-02 counts (19 sent + 20 follow-ups) were likely the last active sends before warmup paused.  
**Root cause:** Complaint rate from early sends exceeded threshold. System correctly paused. No cleanup of list/suppression was done to resume.  
**Fix:** (1) Clean the email list — remove bounced/complained addresses from prospects store. (2) Reset warmup counter. (3) Verify SPF/DKIM/DMARC still valid. (4) Resume with lower batch (5-10/run) and monitor.  
**Files:** `app/platform/auto_outreach.py`, `app/integrations/email_sender.py`  
**Validation test:** `run_email_outreach()` returns `sent > 0` and complaint rate stays <0.25%.  
**Estimated revenue path unlocked:** Restores automated outbound email — currently the ONLY legal automated outreach channel (WhatsApp bulk = ban risk).

---

### Rank 3 — P0: Hot Queue `/app/inbox` Requires Manual Owner Login

**Severity:** P0 — conversion funnel depends on 15-min daily owner manual action  
**Mistake:** The Hot Queue (`/app/inbox`) is the ONLY path from "lead replied" to "offer sent." It requires the owner to: (1) login, (2) review each card, (3) click WhatsApp/Call/Done. No automated follow-up exists for Hot Queue items. The `hot_queue_brief` daily 08:15 IST job generates a text briefing but does NOT take action — it's read-only.  
**Evidence:** `app/platform/office_briefing.py` — `hot_queue_brief` is a briefing generator, not an action taker. `docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md` explicitly states owner must do "15-30 min authenticated `/app/inbox` blitz." `ACTIVE_WORK.md`: "Technical money path = GO; REVENUE GENERATED = WAIT until owner-confirmed UPI bank credit."  
**Revenue impact:** Every hot lead (someone who replied to outreach) sits in queue until owner manually processes it. If owner doesn't login, leads go cold. This is the mid-funnel bottleneck identified since 2026-07-02 and STILL not solved.  
**Root cause:** Deliberate design — human-in-the-loop for outbound contact. But the "human" (owner) is the bottleneck.  
**Fix:** (1) Auto-send WhatsApp draft to hot leads with owner pre-approved template (owner-gated with `HOT_QUEUE_AUTO_WHATSAPP=1`). OR (2) Auto-send email follow-up for hot leads with reply confirmation. OR (3) At minimum, auto-ntfy owner on each new hot lead with 1-click approve action. Current ntfy exists (`LEAD_NTFY_ALERT`) but action is manual.  
**Files:** `app/platform/reply_agent.py`, `app/platform/office_briefing.py`, `app/api/inbox.py`  
**Validation test:** Hot Queue lead enters → action taken within 5 minutes (auto or manual) → lead progresses to offer stage.  
**Estimated revenue path unlocked:** Unblocks the #1 mid-funnel bottleneck. Every hot lead that was dying in queue now gets processed.

---

### Rank 4 — P1: `ready_for_first_paid_customer=false` Despite 1 Paying Customer

**Severity:** P1 — activation gate is lying, blocking automated provisioning  
**Mistake:** `/api/activation/summary` returns `ready_for_first_paid_customer=false` with `blocker_count=1` even though Jiya Makeover IS a paying customer (₹1,999 MRR, INV/2026-27/0001). The `paid_today=0` ledger is correct (no NEW paid today), but the readiness gate should have flipped to `true` after Jiya's activation. This means any automated "new customer" flow that checks this gate will refuse to proceed.  
**Evidence:** Live probe: `{"ready_for_first_paid_customer":false,"payments_ready":true,"blocker_count":1}`. `CURRENT_STATE.md` line 165: "`activation/summary` still `ready_for_first_paid_customer=false` / `blocker_count=1` / `payments_ready=true` — identical to the `c4fc0087` reading."  
**Revenue impact:** If any automated onboarding flow checks this gate, it will block. Also signals to any monitoring/dashboard that the system isn't ready — misleading operators.  
**Root cause:** The activation readiness graph (`graph_version: 2026-06-17-v3`) was built pre-Jiya and has a specific completion criteria that wasn't met (likely some setup step). The blocker is likely `UPI_AUTO_ACTIVATE_CLIENTS` scoping or a setup flag.  
**Fix:** Identify and resolve the single `blocker_count=1` item. Check `app/platform/setup_status.py` for what the blocker is.  
**Files:** `app/platform/setup_status.py`, `app/platform/activation_readiness.py`  
**Validation test:** `/api/activation/summary` returns `ready_for_first_paid_customer=true` after blocker resolved.  

---

### Rank 5 — P1: Sales Autopilot Processes 0 Prospects Per Tick

**Severity:** P1 — engine runs but produces zero revenue actions  
**Mistake:** The sales autopilot scheduler fires hourly (:25), calls `run_tick()`, but processes 0 items because: (a) prospect store has only 25 records, (b) most are already in `emailed` status (outreach was sent 2026-08-03-05), (c) no new prospects are being added (see Rank 1). The `last_tick.json` would show `processed: 0, items: []`.  
**Evidence:** `LAUNCH_READINESS_2026-08-01.md` line 46: "`last_tick.json` at 13:55:00Z = `{enabled:true, dry_run:false, processed:0, items:[]}`". `HOT_QUEUE_AUTOMATION_OPPORTUNITY_SCORE.md` line 14: "Manual refill 2026-08-03 upserted 25 `new` prospects."  
**Revenue impact:** Hourly tick burns compute for zero output. The "autonomous sales engine" is running on empty.  
**Root cause:** Starved input (same as Rank 1). Also, eligibility engine likely filters out prospects that are already `emailed` or `contacted`.  
**Fix:** Solve Rank 1 (feed new prospects). Also verify eligibility engine doesn't over-filter.  
**Files:** `app/platform/sales_autopilot/scheduler.py`, `app/platform/sales_autopilot/eligibility.py`  
**Validation test:** `last_tick.json` shows `processed > 0` within 24h of fix.  

---

### Rank 6 — P1: UPI Payment Verification = Manual Owner Action

**Severity:** P1 — customer pays but activation requires owner bank-check  
**Mistake:** `PROVIDER_VERIFIED` is unreachable BY DESIGN (Stripe + Razorpay removed). The ONLY verification path is `payment_verification_method = owner_confirmed_upi` — owner must check their bank app, find the transaction, and manually approve in admin. `UPI_AUTO_ACTIVATE=1` is armed but scoped to exactly ONE client id in `UPI_AUTO_ACTIVATE_CLIENTS` — not open to new customers.  
**Evidence:** `CURRENT_STATE.md` line 168: "`PROVIDER_VERIFIED` is unreachable BY DESIGN". `memory/decisions.md` ADR-178: "Guest / empty-`client_id` UPI approve is no longer a dead-end." Live probe: UPI VPA `8459012607@axl` is configured, `payments_ready=true`.  
**Revenue impact:** New customer pays via UPI → payment sits as `pending` → owner must manually check bank → approve → customer gets activated. If owner doesn't check, customer waits indefinitely.  
**Root cause:** No bank API integration. UPI is inherently push-based (customer sends money), no webhook callback for most UPI apps.  
**Fix:** (1) Add real-time UPI webhook from bank/processor if available. (2) OR add email notification to owner on every new UPI submission with 1-click approve link. (3) OR expand `UPI_AUTO_ACTIVATE_CLIENTS` to include a whitelist of approved niches/amounts for instant activation (with fraud limits). Currently ntfy alert exists but approval is still manual.  
**Files:** `app/platform/upi_payments.py`, `app/api/upi_payments.py`, `app/platform/ops_alerts.py`  
**Validation test:** Customer submits UPI → owner notified within 60s → approval takes <5 min → customer activated.  

---

### Rank 7 — P1: No Automated Follow-Up Sequence After Initial Outreach

**Severity:** P1 — prospects get one email then go silent  
**Mistake:** `run_email_followups()` exists (Day-3 and Day-7 follow-ups) but is gated by `followup_count < 2` AND requires the prospect to still be in `emailed` status (not replied). However, the warmup pause (Rank 2) means NO emails are going out — including follow-ups. Even when warmup is active, follow-ups only fire if the scheduler job runs AND the prospect hasn't been manually marked.  
**Evidence:** `app/platform/auto_outreach.py` — `run_email_followups()` at line 888+. `SESSION_LOG.md` line 342: "Day-3 followup#1 + Day-7 followup#2."  
**Revenue impact:** 78% of sales require 5+ follow-ups. System sends 1 email then goes silent (warmup aside). Prospects who didn't reply to the first email are never contacted again.  
**Root cause:** Follow-ups are coupled to the same email channel that's paused. No alternative follow-up path (WhatsApp 1-click, SMS, voice callback).  
**Fix:** (1) Fix warmup (Rank 2). (2) Add WhatsApp 1-click follow-up as alternative channel. (3) Add voice callback follow-up for hot-but-unresponsive leads.  
**Files:** `app/platform/auto_outreach.py`, `app/marketing/cadence.py`  
**Validation test:** Prospect receives email Day 0 → no reply → follow-up email Day 3 → no reply → follow-up Day 7 → conversion or suppression.  

---

### Rank 8 — P1: Content Approval Backlog — 422 Pending Items

**Severity:** P1 — customer deliverables stuck in approval limbo  
**Mistake:** 422 `content_approval` items pending: 321 belong to DEAD client ids (un-actionable forever), 101 belong to 3 live clients (jiya-makeover 20, leadgenai-self 53, 0511a69b900e 28). The 101 are NOT technically stuck (customers CAN approve via dashboard) but no reminder email with count/age is sent — only singular "You have content awaiting your approval."  
**Evidence:** `CURRENT_STATE.md` line 146: "422 content_approval pendings: 321 belong to client ids ABSENT from clients_store (8 dead ids), 101 belong to 3 live clients." Line 152: "36 mails sent to jiya-makeover 2026-07-14→08-09, all sent, zero failures, 20 still open."  
**Revenue impact:** Jiya has 20 pending approvals — content was generated but never published/delivered to customer. Customer paid ₹1,999 but isn't receiving the full value of their subscription. Retention risk.  
**Root cause:** Approval notification email is singular, no count/age. Customers don't realize they have 20 items pending.  
**Fix:** (1) Run `retire_orphaned_pending()` for 321 dead-client items (PR #297 exists, not deployed). (2) Improve notification: include count + oldest age. (3) Add daily digest instead of per-item email.  
**Files:** `app/marketing/auto_content.py`, `app/marketing/content_approval.py`, PR #297  
**Validation test:** Dead items retired, live client items reduced from 20 to <5 after improved notification.  

---

### Rank 9 — P1: `WEB_CONCURRENCY=2` Causes 429 on Public Pages

**Severity:** P1 — prospect-facing pages rate-limited under load  
**Mistake:** `WEB_CONCURRENCY=2` (uvicorn workers) means the app can handle only ~2 concurrent requests. Loadtest: `/health` 129×200 OK but `/` (landing page) returns 429 at just 5 concurrent users. Safe anonymous capacity ≈ 3 concurrent users. Any marketing campaign (paid ads, social post, email blast) that drives traffic will hit rate limits immediately.  
**Evidence:** `ACTIVE_WORK.md`: "loadtest `/` 429 at 5 concurrent; safe anonymous ≈ 3 concurrent. Do not raise WEB_CONCURRENCY." `CAPACITY_50_DAY.md`: "WEB_CONCURRENCY=2."  
**Revenue impact:** Every lead magnet (`/audit`, `/site-audit`, `/demo`) and pricing page (`/pricing`, `/start`) is rate-limited. Paid ads would waste budget on 429'd visitors.  
**Root cause:** VPS has limited RAM. Raising `WEB_CONCURRENCY` risks OOM. The rate limiter is too aggressive for the worker count.  
**Fix:** (1) Increase `WEB_CONCURRENCY` to 4 after adding swap. (2) Relax rate limits for anonymous public pages (they're not authenticated). (3) Add CDN/caching for static pages.  
**Files:** `docker-compose.vps.yml`, `app/main.py` (rate_limit config)  
**Validation test:** `/` loads at 10 concurrent without 429.  

---

### Rank 10 — P2: GSC Rank Tracking INERT (No Credentials)

**Severity:** P2 — pSEO observability blind  
**Mistake:** `GSC_ENABLED=0` — Google Search Console integration exists (`app/integrations/gsc.py`) but has no service account credentials configured. The programmatic SEO pages (`/b/{slug}` mini-sites) are generating traffic but there's NO visibility into which pages rank, what keywords drive traffic, or what content to create next.  
**Evidence:** `memory/integrations.md`: "Creds pending, runbook memory/playbooks.md". `CURRENT_STATE.md`: "GSC_ENABLED=0 (creds pending)."  
**Revenue impact:** Without rank data, SEO-driven lead generation is flying blind. Can't optimize content, can't identify winning niches, can't double down on what works.  
**Root cause:** GCP service account + Search Console API not set up.  
**Fix:** Follow `memory/playbooks.md` GSC setup: GCP project → enable API → SA + key → DNS TXT verify → set `GSC_ENABLED=1`.  
**Files:** `app/integrations/gsc.py`  
**Validation test:** `GET /api/clientops/gsc/overview` returns real click/impression data.  

---

## 3. ADDITIONAL VERIFIED ISSUES

### Revenue
- **ADR-104: QA job `TimeLimitExceeded(600)` in DLQ** — 24 dead QA trainer jobs (`dlq:dead=24`). Root cause: KB warmup (`_global: added 9 chunk(s)`) runs 64+ seconds AFTER main() returns, held alive by background threads. Not revenue-blocking but indicates the training/QA pipeline is broken.
- **Invoice counter may be wrong** — INV/2026-27/0001 exists for Jiya but `INV/0002-0013` were VOIDED (2026-07-18). Counter should resume from 0014.

### Sales
- **No lead magnet → inquiry → hot queue automation** — `/audit` generates a score but doesn't create a prospect in the autopilot store. The `submit_inquiry` form saves to a separate `inquiries` store, not the sales autopilot `prospects.jsonl`. Two disconnected stores.
- **WhatsApp 1-click only** — All WhatsApp outreach is manual `wa.me` link. No automated WhatsApp send for sales. This is BY DESIGN (ban-safety) but limits throughput.
- **No SMS channel** — SMS DLT-gated for cold, but even for warm/follow-up SMS doesn't exist.

### Payments
- **Stripe webhook is fail-closed stub** — `POST /api/billing/webhooks/stripe` always returns 503. By design (Stripe removed 2026-07-10) but if anyone tries to pay via Stripe they get 503 with no explanation.
- **Guest UPI bind path CODE-PRESENT but not deployed** (ADR-178, PR #304). Guest pays → needs client binding → dead-end without deploy.
- **No subscription renewal/dunning automation** — `DUNNING_ENGINE=1` in prod but unclear if it's actively sending renewal reminders.

### Voice
- **Voice calling is LIVE but cold outbound only** — `PLATFORM_DIAL_DAILY=1`, cap 100/day. Calls ARE placed (3 real calls 2026-08-02) but conversion from call → customer is untracked.
- **Post-call WhatsApp only** — `POST_CALL_WHATSAPP=1` sends WA to "interested" callers but this is owner-armed, not fully automated.

### Email
- **Warmup paused** (complaint rate 0.449% ≥ 0.25%) — ALL outbound email effectively stopped.
- **Email warmup needs list cleanup** before resume.

### Agents
- **31 STAFF agents defined but most are INERT** — `AGENT_RUNTIME` flag OFF. Only Rohan (email_outreach) and the scheduler jobs are actually executing. 29 agents sit in registry with no trigger.
- **Boss harness not started** — `buzz_start_harness.py --agent Boss` requires owner Desktop NIP-OA mint. Boss can't respond to mentions.
- **DSH runtime armed** (`DSH_RUNTIME_ENABLED=1`) but `DSH_SHADOW_ENABLED=0` and allowlist is 29 agents — running but not shadowed against legacy for comparison.

### Automation
- **Scheduler fires but many jobs process 0 items** — hourly ticks for sales_autopilot, email_outreach, etc. run but with empty inputs.
- **`TEAM_AUTOMATION` flag** controls the whole scheduler — if unset, ALL automated jobs stop.
- **In-process scheduler backup** (`RUN_IN_PROCESS_SCHEDULER`) — if Celery scheduler dies, in-process backup takes over but only when explicitly enabled.

### Infrastructure
- **DLQ has 24 dead tasks** (QA trainer `TimeLimitExceeded`) — not flushed per instructions.
- **Redis queue `celery` = 0** — no pending tasks. Workers are idle.
- **Qdrant running** but RAG usage unclear — KB warmup happens on heavy worker but effectiveness unmeasured.

### Frontend
- **`/app/inbox` requires authentication** — can't verify Hot Queue UX without admin login.
- **Mini-sites `/b/{slug}` generate leads** but those leads go to `inquiries` store, not `prospects` store.
- **429 on public pages** at 5 concurrent — blocks any marketing campaign traffic.

---

## 4. BROKEN / DISABLED TOOLS

| Tool | Status | Evidence | Revenue Impact | Fix |
|------|--------|----------|----------------|-----|
| Sales Autopilot refill | ARMED BUT STARVED | `REFILL=1` but no scheduler invocation | No new prospects enter system | Wire to scheduler |
| Email warmup | PAUSED | Complaint rate 0.449% ≥ 0.25% | All outbound email stopped | Clean list, reset, resume |
| GSC rank tracking | DISABLED | `GSC_ENABLED=0`, no creds | SEO blind | Set up GCP SA |
| Hot Queue brief | OFF | `HOT_QUEUE_BRIEF_DAILY` likely UNSET | No daily revenue briefing | Enable flag |
| Onboard queue | INERT | `CELERY_ONBOARD_QUEUE` UNSET | Can't onboard at scale | Gate after 2nd paid |
| DSH shadow | OFF | `DSH_SHADOW_ENABLED=0` | No A/B comparison | Owner decision |
| Staff Bus | OFF | `STAFF_BUS_ENABLED=0` | Agents can't coordinate | Owner AUTH-MERGE |
| Boss harness | NOT STARTED | Desktop NIP-OA pending | No NL copilot | Owner mint key |
| Stripe | STUBBED | Always 503 | No Stripe payments | By design (UPI only) |
| Prospector scheduler | MISSING | No cron/schedule entry | Zero automated lead gen | Add scheduler job |

---

## 5. PLUGIN & INTEGRATION HEALTH

### WORKING
- **Vobiz telephony** — calls place successfully (~₹0.45/min)
- **EdgeTTS** — free TTS (hi-IN-SwaraNeural)
- **Groq STT** — whisper-large-v3 (primary STT)
- **Mistral LLM** — primary chat model
- **Gemini voice** — 9-key rotation pool
- **Pollinations** — AI image generation
- **ntfy** — phone push alerts
- **Sentry** — error tracking
- **rclone/GDrive** — offsite backups
- **Caddy/TLS** — leadsgenai.in HTTPS
- **Postgres** — primary database
- **Redis** — Celery broker + cache
- **Qdrant** — vector store (running, usage unclear)

### PARTIALLY WORKING
- **Sales Autopilot email** — code works but warmup paused → 0 sends
- **Voice calling** — places calls but conversion tracking absent
- **Postiz** — 6 channels connected but social publishing not verified
- **WhatsApp WAHA** — session working, but auto-send gated OFF

### DISABLED / INERT
- **GSC** — `GSC_ENABLED=0`
- **Staff Bus** — `STAFF_BUS_ENABLED=0`
- **Agent Runtime** — `AGENT_RUNTIME` OFF
- **Dunning Engine** — `DUNNING_ENGINE=1` but effectiveness unknown
- **Cold WhatsApp** — `SALES_AUTOPILOT_WHATSAPP_ENABLED=0` (by design)
- **DSH Shadow** — `DSH_SHADOW_ENABLED=0`

### MISSING / NOT CONNECTED
- **Prospector scheduler** — no automated lead generation job
- **Bank API** — no real-time UPI verification
- **Google Maps API key** — may be expired/limited (used by prospector)
- **GSC service account** — credentials not configured

---

## 6. AI AGENT HEALTH

| Agent | Status | Executes? | Revenue Impact |
|-------|--------|-----------|----------------|
| Rohan (Email Outreach) | CODE-READY, WARMUP-PAUSED | Would execute if warmup active | Primary outbound channel (blocked) |
| Swara (Voice) | FROZEN | YES — places calls | Voice sales (LIVE but untracked) |
| Isha (Content) | CANARY-READY | Generates drafts | Customer fulfillment (Jiya) |
| Zara (Social) | CANARY-READY | Publishes approved content | Social delivery (blocked by approvals) |
| Kavya (Ops) | CANARY-READY | Read-only health checks | Monitoring only |
| Boss (Coordinator) | NOT STARTED | Harness not running | No NL copilot |
| 26 other STAFF | INERT | No trigger/queue | Zero execution |
| Sales Autopilot | RUNNING BUT STARVED | Ticks hourly, processes 0 | Zero revenue actions |
| Hot Queue Brief | OPTIONAL/OFF | Generates text briefing | Read-only (no action) |

**Ghost agents:** 26 of 31 STAFF agents have code, UI, registry entries, but NO trigger, NO queue, NO scheduler job. They exist in `agent_registry.py` as metadata but execute nothing. This is BY DESIGN (canary rollout) but means 84% of the "31-agent workforce" is decorative.

---

## 7. REVENUE FUNNEL FAILURE MAP

```
Traffic (website visitors)
↓ RED — 429 at 5 concurrent, no ads driving traffic, no SEO visibility (GSC OFF)
Lead (inquiry form submission)
↓ AMBER — form works, saves to inquiries store, but NOT auto-routed to prospects
Qualified Lead (prospect in autopilot store)
↓ RED — no automated prospect ingestion; 25 hand-upserted, all already contacted
Contactable Prospect (has email + not yet emailed)
↓ RED — warmup paused, 0 emails sending
Outreach (email sent)
↓ AMBER — emails WERE sent (19 on 2026-08-02) but warmup paused since then
Conversation (reply received)
↓ AMBER — reply triage works, noise filter active, but volume = 0 (no outreach)
Hot Lead (in /app/inbox)
↓ RED — requires owner manual login + 15-min blitz daily
Offer (pricing/plan presented)
↓ AMBER — /pricing and /start work, UPI QR generated, but manual handoff
Payment (UPI submitted)
↓ AMBER — UPI rail works, but verification = owner checks bank manually
Activation (customer provisioned)
↓ AMBER — auto-activate scoped to 1 client; guest bind not deployed
Service Delivery (content generated)
↓ AMBER — auto_content generates drafts, but 20+ approvals pending for Jiya
Retention (renewal/upsell)
↓ RED — no automated renewal reminders, no usage reports, no upsell triggers
Revenue Ledger
↓ AMBER — ledger works (INV/0001, paid_today tracking), but manual UPI confirm required
```

**Biggest leakage:** Traffic → Lead (nobody coming) and Lead → Qualified (no auto-ingestion).

---

## 8. TOP P0 FIXES (Shortest Path to Revenue)

### Fix 1: Wire Prospector/Refill to Scheduler
**Impact:** Unblocks entire funnel. Without this, nothing downstream matters.  
**Risk:** LOW — existing code, just needs scheduler wiring.  
**Dependency chain:** 0 — self-contained.  
**Effort:** 2-4 hours.  
**Action:** Add `staff-prospector-refill` job to `team_scheduler.py` that calls `refill.run()` daily at 10:00 IST. Requires `GOOGLE_MAPS_API_KEY` to be valid.

### Fix 2: Resume Email Warmup After List Cleanup
**Impact:** Restores ONLY legal automated outbound channel.  
**Risk:** MEDIUM — must clean list to avoid re-pausing.  
**Dependency chain:** 0 — self-contained.  
**Effort:** 1-2 hours.  
**Action:** Remove bounced/complained prospects from store. Reset warmup counter. Resume with batch=5. Monitor complaint rate.

### Fix 3: Auto-Ntfy + 1-Click Hot Queue Action
**Impact:** Eliminates 15-min daily manual bottleneck.  
**Risk:** LOW — ntfy infrastructure exists, just needs action wiring.  
**Dependency chain:** 0 — self-contained.  
**Effort:** 3-5 hours.  
**Action:** Enhance `LEAD_NTFY_ALERT` to include 1-click approve/send buttons in ntfy notification. OR auto-send pre-approved WhatsApp draft to hot leads.

### Fix 4: Resolve `ready_for_first_paid_customer` Blocker
**Impact:** Unblocks automated onboarding signals.  
**Risk:** LOW — investigation + flag/config fix.  
**Dependency chain:** 0.  
**Effort:** 1 hour.  
**Action:** Check `setup_status.py` for exact blocker. Resolve it. Verify `/api/activation/summary` flips.

### Fix 5: Increase `WEB_CONCURRENCY` + Add Swap
**Impact:** Landing page handles campaign traffic.  
**Risk:** MEDIUM — must not OOM.  
**Dependency chain:** Requires VPS swap setup first.  
**Effort:** 2 hours.  
**Action:** Add 2GB swap on VPS. Increase `WEB_CONCURRENCY=4`. Re-run loadtest.

---

## 9. 24-HOUR REVENUE RECOVERY PLAN

### Hour 0-2: Fix the Input Problem
1. Verify `GOOGLE_MAPS_API_KEY` is valid and has quota
2. Wire `refill.run()` into scheduler as daily job
3. Trigger manual `refill.run()` to populate prospect store with 25 fresh prospects
4. Verify prospects appear in store: `GET /api/platform/team/prospects`

### Hour 2-4: Restore Email Outreach
1. Remove bounced/complained prospects from store
2. Verify SMTP credentials still valid: `POST /api/admin/owner-email/canary` (send test)
3. Set `EMAIL_WARMUP=0` temporarily OR set `OUTREACH_DAILY_CAP=5`
4. Trigger `POST /api/platform/team/email-outreach/run`
5. Verify `sent > 0` in response

### Hour 4-6: Hot Queue Speed-Up
1. Enable `HOT_QUEUE_BRIEF_DAILY=1` (daily 08:15 IST revenue brief)
2. Verify ntfy alerts fire on new inquiry
3. Test `/app/inbox` authenticated flow (owner login)

### Hour 6-8: Payment Path Hardening
1. Investigate `blocker_count=1` in activation summary
2. Verify UPI submission → admin notification → approval flow end-to-end
3. Check Jiya's 20 pending content approvals — send consolidated reminder

### Hour 8-12: Voice Campaign Review
1. Check if `PLATFORM_DIAL_DAILY` auto-dial fired at 11:30 IST
2. Review call outcomes from any calls placed
3. Verify post-call WhatsApp fired for interested callers

### Hour 12-24: Monitoring + Iteration
1. Monitor email delivery (check SMTP logs)
2. Monitor prospect store growth
3. Monitor Hot Queue item processing
4. Track any new UPI submissions
5. Review DLQ for new failures

---

## 10. DEFINITION OF DONE

Revenue system is not considered fixed until a controlled canary proves:

```
Real lead discovered (prospector finds business)
→ qualification (ICP match, email found)
→ entered into system (prospect store upsert)
→ outreach prepared (personalized Hinglish email)
→ outreach delivered (SMTP send, not 429'd)
→ delivery recorded (prospect status = emailed)
→ reply captured (IMAP triage)
→ reply classified (interested/not_interested)
→ follow-up generated (Day-3/Day-7)
→ sales stage updated (Hot Queue)
→ offer generated (/start → pricing → plan)
→ payment requested (UPI QR shown)
→ payment detected (admin sees pending)
→ payment confirmed (owner approves OR auto-activate)
→ customer created (client record)
→ onboarding triggered (content generation starts)
→ first deliverable generated (poster/article/GBP)
→ revenue recorded (invoice INV/XXXX + ledger)
```

**Current state: Steps 1-4 worked ONCE (2026-08-03 manual refill + email). Steps 5+ partially work. Steps 8+ require owner manual action. Steps 12+ work but are bottlenecked. No step is fully automated end-to-end without human intervention.**

---

**Generated:** 2026-08-15 06:30Z  
**Prod:** `91958c23` | **MRR:** ₹1,999 | **Customers:** 1 | **Today's paid:** 0  
**Canary:** 🐦 pelican
