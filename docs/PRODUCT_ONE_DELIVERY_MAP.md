# Product One (AI Automated Marketing) — Delivery Map

> Verified 2026-07-09 by read-only whole-repo audit (routes, wiring, DB, scheduler, agents, tests).
> **Ground truth = code.** Customer-facing delivery data is JSONL-file-backed under `data/`
> (delivery ledger, content queue, clients_store, approvals); `customer_deliverables` +
> `automation_logs` DB tables are best-effort mirrors. Read-visibility features go against
> `app/marketing/*` services, not raw DB queries.

## 0. TL;DR — the honest state

Most of the "build it" ask **already exists and is wired**. The real problems are (a) one
broken customer-milestone event, (b) the structured automation-log feed had **no UI**, and
(c) most *push* delivery (auto-publish to social/WhatsApp/report-email) is **INERT by default**
behind env flags — so a paying customer today sees generated **drafts + approvals + a pull
timeline + a monthly report file**, but rarely an auto-"published" proof line until an operator
connects Postiz/WhatsApp and flips flags.

Pricing truth stays in `app/marketing/packages.py`. Product One = Main ₹1,999 / Advanced ₹5,999.

## 1. Delivery Map (per deliverable)

| Deliverable | Backend endpoint | Frontend | Store / model | Worker/job | Status | Customer-visible proof today |
|---|---|---|---|---|---|---|
| **Social Setup Wizard** | `GET/POST /api/customer/profile`, `GET/POST /api/customer/social/config` (`customer_dashboard.py:1150/1188/1386/1423`) | in-page tabs `customer_dashboard.html` (~2574/2641) | `data/social_config.jsonl` via `social_engine/client_config.py` | sync save; seed → Celery `seed_first_week` | **working** (persistence real) | Checklist %, saved handles/prefs pre-filled, honest per-channel status board |
| Social milestone (socials connected) | `_sync_social_delivery_stage` (`customer_dashboard.py:1466`) | timeline | `delivery_ledger` `social_setup_completed` | — | **FIXED this session** (was broken: TypeError swallowed → event never logged) | Timeline line "Aapne social accounts connect kar diye" |
| **Content pipeline (draft→approval)** | draft via `auto_content.run_daily_content()` | Calendar + Approvals tabs | `data/content_queue/<cid>.jsonl` | scheduler `content` daily 07:00 | **working** | Drafts in Calendar; approvals queue |
| Social publish (IG/FB) | `social_engine.enqueue_publish` / Postiz (`providers.py`) | — | `social_post_jobs` (lazy) | `content` job bridge | **partial (INERT)** — `SOCIAL_ENGINE`/`POSTIZ_API_KEY` unset → draft-only | Rare `post_published` until connected |
| GBP posting | none (marked "soon"/manual) | wizard state | — | — | **missing** (external API approval blocked) | Manual only |
| **Creatives / images** | `POST /api/customer/studio/ai-image`, `/complete-post` (`customer_marketing_studio.py:791/829`); proxy `/api/marketing/ai-image-proxy` | Studio | `data/ai_images/` (SHA1 cache); `brand_frames` SVG feed | daily branded-feed | **working** (gen+proxy) / partial: images not pinned as ledger proof | Studio image URL; `/branded-feed` 3 daily posters |
| **WhatsApp (WAHA)** | `/api/wa/*` (`whatsapp.py:38`); `WhatsAppProvider.publish` | `whatsapp.html` + hot-queue reply links | `data/wa_*.jsonl` | hourly `wa_campaign_runner.run_due()` | **working** (ban-safe 1-click; auto real but `WHATSAPP_AUTO_SEND=0`) | Prefilled `wa.me` reply links |
| **Approvals** | `GET /api/customer/approvals/pending`, `POST /api/customer/approvals/{id}/decide`; public token approve | approvals queue + public HTML page | `data/content_approvals.jsonl` | — | **working** | 1-click approve/reject queue |
| **Customer Delivery Status** | `GET /api/customer/timeline`, `/api/customer/delivery-proof` (`customer_dashboard.py:1498/1517`) | in-page timeline | `delivery_ledger` + `product_one_delivery` | health/recovery sweep | **working** | "AI ne aapke liye kya kiya" timeline |
| **White-label monthly report** | `client_report.build_report()` | HTML file | `data/client_reports/<id>_<YYYY-MM>.html` | scheduler `client_report.run_monthly()` | **working** (file always written; **email gated `CLIENT_REPORTS`**) | Monthly report incl. delivery-proof counts + "AI team ne kya kiya" + Hinglish next-steps |
| **Admin Delivery Cockpit** | `GET /api/admin/delivery-cockpit`, `/delivery-logs`, `POST /clients/{id}/delivery-action` (`admin_dashboard.py:380/396/421`) | `/app/delivery-command-center` → `delivery_command_center.html` (admin landing) | reads `delivery_ledger` + `product_one_delivery` | health sweep | **working** | (admin) per-customer health, channels, approvals, failures, next-action |
| **Automation Logs (structured, ADR-064)** | `GET /api/admin/automation-logs` (`admin_dashboard.py:448`) | **NEW this session**: "Automation Runs" panel in `delivery_command_center.html` | `automation_logs` DB table (JSONL fallback) | every job via `_run_job` choke-point | **was API-only → NOW wired to UI** | (admin) job/customer/status/time/retry/error feed with filters |
| **Delivery ledger (events)** | `delivery_ledger.py` (19 event types) | timeline / cockpit | `data/delivery_ledger/<cid>.jsonl` | many callers | **working** (1 event fixed this session) | Underlying event stream for timeline + report |
| **Agents page** | `/api/agents/roster` etc. | `/app/agents` (+`/app/agent-tools`) | `agents`/`agent_events` DB | — | **working** | (admin) roster + coordination |

## 2. Automation & agent visibility

- **~38 scheduled jobs** all funnel through `team_scheduler._run_job` (`:213`) → dual-write: dead-man
  heartbeat (`automation_health.record_run` → `data/job_runs.jsonl` + `job_heartbeats.json`) **and**
  structured `AutomationLog` DB (ADR-064) at `status="running"` (start) + `success/failed` (finish).
- **33-member agent roster** in `app/platform/team.py:41` (Boss, Swara, Isha, Nikhil, Arnav, …) →
  events log to `agent_events` DB; surfaced on `/app/team`, `/app/office`, `/app/agents`.
- **Structured-log field coverage (post-fix):** job id ✓, job_type ✓, status ✓, started/finished ✓,
  duration ✓, error_message ✓, **output_summary NOW populated** (this session). Still dormant:
  `retry_count`/`next_retry_at` (Celery retries not fed back), `client_id` (always platform-level for
  the 38 jobs → no per-customer job trail yet), and **no proof/artifact column** (would need
  migration `011`). Event-driven tasks (`onboard_client`, `seed_first_week`, `process_tick`) + the
  ~14 watchdog sub-engines are outside the structured log.

## 3. Recommended navigation (Task 7 — proposal, NOT yet applied)

Applying page hides/merges is **deferred** (risky; working tree already dirty from another session).
Proposed target once approved:

- **Customer:** Today (timeline/home) · Setup (wizard) · Approvals · Calendar · Reports.
  (All exist as in-page tabs in `customer_dashboard.html` — this is a relabel/reorder, not new pages.)
- **Admin:** Delivery Cockpit (landing) · Customers (`/app/clients`) · Automations (Mission Control
  `/app/automation` + the new Automation Runs panel) · Agents (`/app/agents`) · Failed Jobs (Automation
  Runs → "Failed" filter) · Plans/Billing.
- **Hide/merge candidates (verify before touching):** `/app/battlecard` (static), `/app/explorer`
  (mostly static), `/app/command-center` (already 307→control-center). Gated-dormant pages
  (`journeys`, `flows`, `admin/db`, `impersonate`) stay behind their flags.

## 4. Gaps / pending (prioritized)

1. **Publish proof** — connect Postiz + flip `SOCIAL_ENGINE` so `post_published` actually fires (biggest "customer sees nothing published" gap). External + operator action.
2. **Report email** — `CLIENT_REPORTS=1` (or `send=True`) so the monthly report is delivered, not just written to disk.
3. **Per-customer job trail** — set `client_id` on customer-scoped automation runs so the Automation Runs panel can filter by customer meaningfully (currently platform jobs log blank client_id).
4. **Proof/artifact field** — add `evidence_url`/artifact id to `AutomationLog` (migration `011`, down_revision `010`) + pin creative image URLs to `post_published` events.
5. **Retry visibility** — feed Celery `run_staff_job` retries + DLQ backoff into `retry_count`/`next_retry_at`.
6. **Page simplification (Task 7)** — apply the nav above after explicit go-ahead.

## 5. This session's changes (uncommitted — review the diff)

- `app/api/customer_dashboard.py` — removed invalid `customer_visible=True` kwarg on the
  `social_setup_completed` ledger call (was throwing `TypeError`, swallowed by `except: pass`);
  added idempotency `key`. **Milestone now records.**
- `app/platform/team_scheduler.py` — `_run_job` finish log now populates `output_summary`
  ("success in Nms" / error-class) so admin logs aren't blank.
- `frontend/delivery_command_center.html` — new **"Automation Runs"** admin panel consuming the
  ADR-064 `GET /api/admin/automation-logs` DB endpoint, with filters: status (All/Success/Failed/
  Running/Skipped), job-type, customer id, date-range; columns Job/Customer/Status/Time/Retries/When/Detail.
- `tests/test_social_setup_ledger_fix.py` (new, 3 tests — RED-first: fail on unfixed code).
- `tests/test_automation_runs_panel.py` (new, 4 tests — node syntax + no-removal guard + markers).

No new routes added (uses existing endpoint) → no duplicate-route risk. No secrets. No compliance
gate touched. No auto-publish/auto-send enabled.

## 6. How to verify (Windows `.venv`) + deploy

```bat
:: from repo root
.venv\Scripts\python.exe -m pytest tests\test_social_setup_ledger_fix.py tests\test_automation_runs_panel.py ^
  tests\test_delivery_ledger_wiring.py tests\test_automation_logs.py tests\test_social_setup_wizard.py -q
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe scripts\check_secrets.py
```
All three must pass (prod_check runs the frontend wiring audit that checks every `fetch()` path
resolves — the new panel calls the already-registered `/api/admin/automation-logs`). Then follow the
`leadgen-ops` skill deploy SOP (git push → SSH rebuild+recreate → 2× `/health`=`environment:production`).
**Deploy only on your explicit go-ahead.**

## 7. Product One delivery checklist

- [x] Customer can complete setup wizard (profile/offer/social/WhatsApp/brand+approvals) — persists
- [x] "Socials connected" milestone shows on timeline — **fixed**
- [x] Content drafts generate + land in approvals queue
- [x] Customer can approve/reject (1-click)
- [x] Customer sees a pull timeline of what the AI did
- [x] Monthly white-label report generated (with delivery-proof counts)
- [x] Admin Delivery Cockpit shows per-customer health + next action
- [x] Admin can see structured automation-run logs with filters — **new panel**
- [ ] Auto-publish to IG/FB (needs Postiz connect + `SOCIAL_ENGINE=1`)
- [ ] GBP direct posting (external API approval)
- [ ] Report auto-emailed (needs `CLIENT_REPORTS=1`)
- [ ] Per-customer automation-run attribution (`client_id` on jobs)
- [ ] Proof artifact IDs on published events (migration `011`)

## 8. AI model routing / PII note (from the brief)

- The **app's runtime** already uses a free-only LLM chain with fallback + 429 circuit-breaker
  (`app/voice_agent/free_ai.py`) — no paid STT/TTS/LLM (user mandate). A separate *dev-time* model
  router (cheap models for scan, GLM/Qwen for impl, Claude for review) is a workflow choice outside
  the product code; if wanted, add it as tooling config, not app runtime.
- **PII masking:** all work this session was local repo edits — **no customer PII was sent to any
  external model.** If external LLMs are used for repo tasks, mask names/phones/emails/addresses/
  keys/lead data first.
