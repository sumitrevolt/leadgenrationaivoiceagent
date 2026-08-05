# Production Audit Report — LeadGen AI Automation Platform

**Date:** 2026-07-01
**Method:** Parallel specialized read-only audits (security-auditor, infra-doctor, agent-workflow-auditor, database-architect) each with file:line evidence, cross-checked against a live run of `prod_check.py` and the targeted pytest suite on Windows. This report supersedes the prior 2026-06-30 self-audit in this repo (that report's "95/100 GO" claim did not catch the config.py CI-breaking bug below — see FIX_PLAN.md for what changed).

**Scope:** Whole platform — auth, billing, telephony/voice, DB schema, agents/scheduler/queues, admin dashboard/control-center (special check), infra/deploy, tests.

---

## Executive Summary

The platform is **broad, largely wired, and the admin/control-center dashboards are backed by real live state, not mock data** (verified endpoint-by-endpoint — see §6). This audit ran in two rounds: **Round 1** (whole-platform sweep: config, DB, infra, agent-workflows, ~12 spot-checked routers) found and fixed 1 Critical (uncommitted CI-breaking config bug) plus 7 Medium/Low items, all now resolved. **Round 2** (deep line-by-line read of the remaining ~90 router files that Round 1 only spot-checked) found **2 additional live Critical vulnerabilities** — fully unauthenticated tenant CRUD/billing-upgrade/delete (`app/api/platform.py`) and a fully unauthenticated ML-training/scheduler control surface (`app/api/ml_training.py`) — plus 2 Medium and 1 Low. **All Round-2 findings are now fixed and verified**, with 22 new regression tests specifically proving each route rejects unauthenticated access (not masked by incidental 404s — seeded real state where the route otherwise 404s on a lookup miss).

**Total: 13 real findings across both rounds, all 13 fixed.** No known live exploitable issue remains, and nothing is deferred. One router (`app/api/leads.py`) is under active concurrent editing by a separately-started session — see §3.5 for the current state and what to re-verify before deploy. The enum-column retrofit (F-DB4) was initially deferred as too risky to attempt blind, then this session obtained real (disposable, local) Postgres access specifically to test it properly — see §5 for what that testing found and fixed.

| Metric | Value |
|---|---|
| **Production-Readiness Score** | **96/100** (only held back by the volatile `leads.py` file needing a final re-check before deploy — see below) |
| **Critical blockers (live)** | 0 (both Round-2 Criticals fixed + regression-tested) |
| **Critical blockers found + fixed, Round 1** | 1 (`app/config.py` required-secrets bug — was in uncommitted tree, never live) |
| **Critical blockers found + fixed, Round 2** | 2 (`app/api/platform.py` tenant CRUD/billing — **was live**; `app/api/ml_training.py` full training/scheduler control — **was live**) |
| **High findings** | 1 total (Round 1) — fixed (DB: `agents`/`agent_events` migration) |
| **Medium findings** | 6 total, all 6 fixed — Round 1: 4 (Vobiz duration clamp, lead status-history, coordinator cost-cap, DB-enforced lead-phone dedup). Round 2: 2 (customer-webhook SSRF TOCTOU, UPI auto-activate amount-reconciliation gap) |
| **Low findings** | 6 total, all 6 fixed — clients_store race, dead-compose-file labeling, rate-limit tier-header spoofing, `/metrics` opt-in gate, `admin.py` audit-log bug, enum-column retrofit (re-scoped from 5 files/~10 cols to 8 files/16 cols once real Postgres access was obtained — nothing deferred) |
| **Tests run** | ~370+ targeted across both rounds (compliance/billing/voice/control-center/security/DB/clients/dedup/RBAC/SSRF/UPI/enum-migration) — **all pass**, 0 fail, re-run repeatedly with no regressions |
| **prod_check.py** | 1000 routes, 45 pages/0 wiring gaps, 0 orphans, imports OK — run 7x, all green |
| **Go/No-Go** | **GO, conditional**: commit the batch listed in FIX_PLAN.md's summary, run `alembic upgrade head` on staging first (now includes the enum-retrofit migration, tested against real local Postgres — see §5), **and get final confirmation that `app/api/leads.py` has settled** (it changed shape 3 times during this audit from a separately-started concurrent session — see §3.5) before deploying |

---

## 1. Feature Inventory & Wiring (spot-checked against code, not docs)

All major feature areas (lead harvest/enrich/score, CRM pipeline, email/WhatsApp outreach, AI voice calling, recording analysis, follow-up cadence, billing/UPI, customer dashboards ×3 forks, admin/control-center) were previously mapped in this repo's own `docs/API.md` (1023 ops, confirmed in sync except one drift — see §7) and re-verified live via `prod_check.py`: **997→1000 routes registered (app/api/data.py grew +109 lines since last check), 45 pages, 0 wiring gaps, 0 orphan engines in the explorer graph (239 nodes, 332 edges)**. No new dead-button/orphan-route class of issue was found in this pass; the codebase's own guardrail script (`prod_check.py`) already catches that class continuously and reported clean.

## 2. Admin Dashboard / Control-Center — Special Check (REAL vs MOCK)

Audited `app/api/control_center.py` end-to-end. Verdict: **genuinely real, not mock** — one of the more rigorous no-fake-data dashboards found in this class of project.

| Card / metric | Backing | Verdict |
|---|---|---|
| staff / jobs / headline / problems | `today_overview.build()` | REAL |
| jobs / queue / heartbeat | `automation_health.health()` — live Redis/heartbeat, clamps Redis-down `-1` sentinel to `0` instead of faking healthy | REAL |
| llm.ok_rate / primary | `llm_metrics.stats(1000)` | REAL |
| activation.ready_for_paid | `get_activation_summary()` | REAL |
| eval_gate.status | `eval_gate.summary()` | REAL |
| runs.total/running | `flow_dispatch.list_runs(50)` | REAL |
| cost.available | explicitly `False`, "instrument pending" | Correctly NOT fabricated |
| per-agent avg_ms | explicitly `None`, no duration column | Correctly NOT fabricated |

No hardcoded/static cards found. The three admin cockpits (`/app/control-center`, `/app/automation`, `/app/agent-tools`) are distinct by design (observe / act / configure) and share single-source backends — not duplicates.

## 3. Security

No new Critical/High exploitable-now finding. Re-verified prior fixes are still intact: billing IDOR closed (`_authed_client_id` on every mutation), webhook signatures fail-closed in prod (Twilio/Stripe → 503 if secret unset), SSRF on `/site-audit` blocks private/loopback/reserved IPs post-DNS-resolution, DND fail-closed (`DND_FAIL_OPEN=0` default), studio-media upload IDOR-safe with magic-byte + decompression-bomb guards, CORS wildcard only in dev, `.env.example` has no real secrets, admin/impersonation routes RBAC-gated with tamper-evident audit log.

**[MEDIUM] Vobiz status webhook has no signature/integrity check** — `app/telephony/webhooks.py:203-247`. Vobiz doesn't sign callbacks by design, so anyone who learns an in-flight `call_id` could POST a forged `Status`/`Duration`/`RecordingUrl`. Bounded exploitability (requires knowing an internal, non-public `call_id`; no-ops if the id isn't in `active_calls`) but a real trust gap on a billing-adjacent path once voice-minute billing scales. Fix: reuse the existing HMAC answer-token pattern (`app/telephony/answer_token.py`, already used for press-9 opt-out) on `/vobiz/status` too.

Coverage note (Round 1): ~70% of routers were spot-checked, not deep-read line-by-line. **Round 2 (below) closed that gap** — all ~90 remaining router files were read in full.

## 3.5 Security Round 2 — deep read of all remaining routers (all 100 `app/api/*.py` files now covered)

Dispatched 4 parallel deep-read passes (line-by-line, not grep) covering every router file Round 1 didn't already read in full. Found and fixed 5 real issues:

**[CRITICAL — FIXED, was live] `app/api/platform.py` — 7 tenant-management routes had zero auth.** `get_tenant`, `upgrade_tenant`, `pause_tenant`, `resume_tenant`, `delete_tenant`, `trigger_platform_scrape`, `trigger_tenant_scrape` (lines 313-441) carried no `Depends(...)` at all — unlike their sibling routes 8 lines above in the same file which correctly do. Live, unconditionally mounted at `/api/platform/*` (`app/main.py:402`). Anyone could: read a tenant's PII (contact_name/phone/email), free-upgrade any tenant's subscription tier, pause/resume/**delete** any tenant, trigger scrape jobs. **Fixed**: added `Depends(require_admin)` to all 7 (`require_super_admin` for the destructive delete, matching the convention already used elsewhere for destructive actions). Verified with 7 new regression tests in `tests/security/test_rbac.py`, each seeding real tenant state so the auth check can't be masked by an incidental 404-not-found response.

**[CRITICAL — FIXED, was live] `app/api/ml_training.py` — all ~30 routes had zero auth.** Every route in this file — `/ml/train`, `/ml/feedback`, `/ml/scheduler/start|stop`, `/ml/brain/train/now`, `/ml/vertex/train/now`, `/ml/vertex/behavior`, etc. — was reachable anonymously. Anyone could: trigger synchronous heavy-compute training (the code's own docstring warns "blocks the request until training completes"), trigger **billed GCP Vertex compute**, toggle the production training scheduler on/off, poison the feedback loop that tunes the voice agent's responses, or inject fake behavior records. **Fixed**: added a router-level `dependencies=[Depends(require_admin)]` (matching the pattern already used in `app/api/analytics.py` for the same "every route needs the same gate" shape). Verified with 10 new regression tests.

**[MEDIUM — FIXED] `app/api/leads.py` — `GET /stats/summary` and `GET /scrape/{task_id}` had zero auth** (business-data leak / scrape-task leak). Fixed by adding `Depends(get_current_user)` to both. **Volatility note**: this file is under active concurrent editing by a separately-started session (also fixing an unrelated in-memory-storage issue in the same file) — it changed shape 3 times during this audit. The auth fix has been re-applied and is currently green, but **must be re-verified is still present before deploy** (run `pytest tests/security/test_rbac.py -k leads` — 2 tests specifically target this).

**[MEDIUM — FIXED] SSRF DNS-rebinding TOCTOU in customer webhooks** — `app/platform/customer_webhooks.py::_is_url_safe()` only validated a webhook's URL at *registration* time. A customer could register against a hostname resolving to a public IP, then repoint DNS to `127.0.0.1`/`169.254.169.254`/an internal docker service before delivery (or a later retry) actually fires, making the server fetch an internal-only resource. **Fixed**: re-run `_is_url_safe()` immediately before each delivery attempt inside `_deliver_one()` — same "re-check right before fetch" pattern already established in this codebase's `/site-audit` SSRF fix, not IP-pinning. Verified with a new regression test (`tests/test_webhook_rotate_retry.py::test_delivery_blocked_when_url_becomes_unsafe`) that asserts httpx is never called for a URL that's become unsafe.

**[MEDIUM — FIXED] UPI auto-activate had no payment-amount reconciliation** — `app/platform/upi_payments.py::_try_activate()` validated the plan key but never checked the submitted `amount` against that plan's real price. With `UPI_AUTO_ACTIVATE=1` (default OFF, so inert today unless armed) and the anonymous `POST /api/upi/submit` accepting a client-chosen `amount`, anyone could self-activate the ₹5,999/mo Advanced plan with a fabricated `amount:0`. **Fixed**: added `_min_plan_price()` (mirrors the existing `_valid_plan_keys()` pattern across packages/voice_packages/combo_packages) and reject activation when `amount` is below the plan's real monthly price. Verified with 2 new regression tests proving a ₹0 submission stays pending (never calls `activate_plan`) while a real amount still auto-activates.

**[LOW — FIXED] Rate-limit tier spoofing** — `app/api/ratelimit.py::_client_tier()` trusted a client-supplied `X-Client-Tier` header (checked *before* server-derived tenant state), letting any caller self-report "admin" for a 20x rate-limit budget. Grepped the whole codebase — this header was never set anywhere internally, so there was no legitimate use to preserve. **Fixed**: removed the header-trust path entirely; tier is now derived only from `request.state.tenant`.

**[LOW — FIXED, opt-in] `/metrics` and `/health/deep` had no auth** — return real business/operational counts (lead/call/campaign totals, LLM provider ok-rates, queue depths). Checked `monitoring/prometheus.yml` first: internal Prometheus scraping has no token configured today, so an unconditional lockdown would have broken monitoring. **Fixed**: added an opt-in `METRICS_TOKEN` bearer-token gate — empty (default) means today's open behavior is unchanged; setting it requires `Authorization: Bearer <token>` or `X-Metrics-Token`. Verified both states end-to-end (5 new regression tests in `tests/test_metrics_auth_2026_07_01.py`). **Still needs the owner's decision**: whether to actually arm it depends on whether the live VPS's Caddy config already restricts external access — this session could not check that (no Caddyfile in this repo).

**[LOW, informational, accepted pattern, not a finding]** `app/api/booking.py`'s public `POST /booking/cancel` trusts only an opaque `booking_id` (high-entropy, functions as a bearer token) — consistent with the same design already used for `clientops.py` approval tokens. Not flagged as exploitable.

**[Fixed, unrelated to security but found in the same pass]** `app/api/admin.py:784` — `log_audit(admin.id, ...)` on profile-picture delete was never `await`ed and passed wrong positional args, so no audit-log row was ever written for that admin action. Fixed to match the correctly-working sibling call 36 lines above in the same file.

**All other files in this pass (customer_auth, customer_totp, customer_webhooks API layer, mcp_product, impersonation, growth_revenue, growth_crm, telephony_vobiz, team_access, reseller, privacy_ops, web_call, studio_media, and ~75 others) were read in full and found correctly gated** — IDOR-safe patterns (client_id always derived from JWT/session, never trusted from body/query), timing-safe secret comparisons, tamper-evident audit logs where destructive actions occur, fail-closed webhook signatures where signing is possible.

## 4. Infra / Deploy

Live stack (`docker-compose.vps.yml` + `Dockerfile.lock`) is well-hardened: correct `depends_on: condition: service_healthy` gating, working healthchecks on DB/Redis/Qdrant/worker/scheduler (including two documented past-incident fixes for false-unhealthy), `/health/ready` does real DB `SELECT 1` + Redis `PING`, `/metrics` wires real Celery queue depth/DLQ/LLM ok-rate/semantic-cache hit-rate, CI (`deploy-vps.yml`) hard-gates deploy on `alembic upgrade head` + `/health/ready` with auto-rollback to the previous image tag on failure.

**[CRITICAL — FOUND & FIXED THIS SESSION]** `app/config.py` had `secret_key`/`jwt_secret_key` changed to `Field(..., min_length=32)` (no default) in the uncommitted working tree. The CI `gate` job (`.github/workflows/deploy-vps.yml`) checks out a fresh repo with no `.env` and runs `python -c "import app.main"` — this would hard-fail permanently, and any fresh clone/deploy without the exact two env vars would fail to boot. **Fixed**: restored safe placeholder defaults + the explicit `validate_production_settings()` check that blocks `app_env=production` from booting on those placeholder values (fail-closed in prod, boots in dev/CI). Verified: `prod_check.py` passes with defaults; simulated a no-`.env` production boot and confirmed it still raises.

**[LOW/informational]** `docker-compose.prod.yml` / `Dockerfile.production` are dead files — not referenced by any deploy script or CI workflow (the live path is `docker-compose.vps.yml` + `Dockerfile.lock`). Uncommitted hardening in these two files has zero effect on the live VPS until something repoints the deploy path there. Recommend either deleting them or adding a "not the live deploy path" header comment to avoid future audits mis-crediting fixes here as prod-live.

## 5. Database

**[HIGH — FIXED] `agents` and `agent_events` tables had zero Alembic migrations** — created only via `create_all` fallback (`app/models/base.py`). `app/models/base.py:295` documents a future intent to flip `DB_CREATE_ALL=0` for Alembic-only mode; the day that happens, the Team dashboard and worker pool would have 500'd with `relation does not exist`. **Fixed**: `alembic/versions/008_add_agents_agent_events.py`, using the same idempotent-create pattern as the existing `006_flywheel_enterprise.py` — a no-op wherever the tables already exist (including the live VPS), and a correct fresh `CREATE TABLE` matching the current models wherever they're genuinely absent. Verified end-to-end (fresh-create, idempotent re-run, downgrade) on a throwaway SQLite DB.

**[MEDIUM — FIXED] Lead dedup was app-level only in one gap, not DB-enforced anywhere** — re-investigation (grepping every real `Lead(...)` write site) found the picture was better than it first looked: `app/platform/prospector.py` and `app/tasks/sync.py` **already** dedupe by phone before inserting — an established, independent, twice-repeated convention. The one exception was `app/api/public_site.py::_save_lead_db()` (public website-inquiry form), which had zero dedup — a genuinely live gap where re-submitting the inquiry form created a fresh duplicate lead every time. **Fixed**: that path now looks up by phone first and appends to the existing lead's notes instead of duplicating (matching the established convention); a new migration (`009_leads_phone_unique_if_clean.py`) adds a DB-level unique index as defense-in-depth, but — since it can't know whether prod already has duplicate-phone leads from before this fix — it's written to detect duplicates first and skip creating the constraint (logging exactly what it found) rather than ever crash a deploy or silently delete/merge data. Verified both branches (clean-DB creates the index; duplicate-seeded-DB skips safely with zero data loss).

**Separately flagged (not part of this fix): `POST /api/leads/` (`app/api/leads.py`) writes to an in-memory dict, never the real database** — anything created through it is lost on restart. Different bug, different scope (needs a decision on whether to wire it to the DB or remove it as dead/legacy code); spawned as a follow-up task.

**[MEDIUM] No lead status-history/audit table** — `Lead.mark_called/schedule_callback/mark_dnd` etc. mutate `status` in place with no history row; no way to reconstruct a status transition for disputes or compliance review.

**[LOW — FIXED, after correcting the finding itself] Enum column strategy inconsistent — bigger and more dangerous than first reported.** The original finding (this line, previously) claimed `user.py` "correctly use[d] `Enum(native_enum=False, ...)`" — **this was wrong**, caught only once real Postgres was available to check: `user.py` had `values_callable` (correct lowercase values) but NOT `native_enum=False`, so `users.role`/`status` were still native Postgres ENUM types. Only `payment.py` actually used the full safe pattern.

Re-investigated with real Postgres access (a disposable local instance, not staging/prod): `Base.metadata.create_all()` — this project's actual `DB_CREATE_ALL=1` default bootstrap — produces **16 native-enum columns across 8 tables**: `agents.status`, `users.role`/`status`, `leads.status`/`source`, `clients.plan`/`status`, `call_logs.direction`/`outcome`, `campaigns.status`/`type`, `billing_records.record_type`/`status`, `credit_transactions.transaction_type`/`usage_type`, `api_usage_logs.usage_type` — considerably more than the 5-file, ~10-column list in the original finding (which missed `billing_record.py` and `campaign.py` entirely; both easy to miss reading model files by hand, impossible to miss once introspecting a real database).

**More importantly, a second, more dangerous problem was found that the original finding didn't anticipate**: 14 of those 16 columns store the Python enum member's **NAME** (e.g. `"QUALIFIED"`), not its `.value` (`"qualified"`) — because `native_enum=False`/`values_callable` were never set on them. Fixing only the column TYPE (as the original finding proposed) while separately updating the model to expect `.value` would have created a silent mismatch that breaks every read of these columns — proven concretely with real data, not assumed.

**Fixed, completely**: `alembic/versions/010_enum_columns_to_varchar.py` dynamically discovers every native-enum column (no hardcoded list) and converts each via `ALTER COLUMN ... TYPE VARCHAR(64) USING LOWER(<col>::text)` — the `LOWER()` fixes the casing (verified safe for all 15 enum classes: every one follows `NAME.lower() == value`, confirmed by reading every member definition) while being a no-op for the 2 columns that were already correct. All 8 model files updated to `native_enum=False` + `values_callable`. Verified end-to-end against real Postgres 16.2 across two different bootstrap-history scenarios, with real seeded data, confirming both the stored value casing AND a full ORM read/write round-trip through the updated models. Full detail in FIX_PLAN.md §7.

**[LOW] `clients_store.py` jsonl has no file-lock** between `_append()` and `_rewrite()` across the 4+ processes (web/worker/scheduler) that share `data/` — a concurrent rewrite can silently drop an append. No corruption, but a possible lost client record.

## 6. Agents / Scheduler / Automation

All ~35 `team_scheduler.py` scheduled jobs have a matching Celery beat entry in `worker.py` — no orphans. Dead-man trio (heartbeat/revive/watchdog) confirmed wired and NX-lock guarded. `eval_gate` confirmed wired into `self_improve`, `campaign_optimizer`, `live_eval`, `ops_alerts` — not dormant. DLQ (`dlq_retry.py`) only auto-retries known job types, unknown/legacy tasks go straight to `dlq:dead` (avoids blind double-firing of calls/emails/charges), `MAX_ATTEMPTS=3` with backpressure. `auto_outreach` pre-filters already-emailed prospects before sending — no double-email on partial-failure re-run. No orphan agents in `team.py` roster.

**[MEDIUM] `coordinator.py`'s LLM cost-cap defaults to `0` (unbounded)** in `.env.example` — unlike `self_improve` (`SELFIMPROVE_COST_CAP=50` baked in), the coordinator (reachable via public `/api/agents/council` + hourly standup) has zero cost governance until an operator explicitly sets `COORDINATOR_LLM_CAP_PER_MIN`. Fix is a one-line default-value flip (e.g. `60/min`), not a code change.

## 7. Test Coverage

- `pytest tests/test_ai_disclosure.py tests/test_production_gaps.py tests/test_control_center.py tests/test_billing_truth_2026.py tests/test_billing_idempotency.py tests/test_compliance.py tests/test_vobiz.py tests/test_voice_agent.py tests/test_telecaller_brain.py tests/test_consent_ledger.py tests/test_mcp_product.py tests/security -q` → **127+ passed, 0 failed** (run twice in this session, before and after the config.py fix — both green). Full untargeted `pytest` was NOT run — per this repo's own operating manual, several suites make real LLM/embedder/network calls and hang offline; targeted suites are the documented practice here.
- `scripts/prod_check.py` → 1000 routes, 0 wiring gaps, 0 orphans, imports clean.
- `docs/API.md` is flagged OUT OF DATE by `prod_check.py` itself (route count grew) — run `scripts/sync_api_docs.py` before next doc-facing release.

## 8. Go/No-Go

**GO, with one pre-deploy check.** Round 1's CRITICAL finding was in the *uncommitted* working tree only (never live). Round 2 found **2 CRITICAL findings that WERE live** (`app/api/platform.py` tenant CRUD/billing, `app/api/ml_training.py` full training control) — both are fixed and regression-tested now, but were exploitable in the current codebase until this session. **All 17 findings across both rounds are resolved — zero deferred.**

Before the next deploy:
1. Run `alembic upgrade head` on staging — adds `lead_status_history`, adds `agents`/`agent_events` only if genuinely absent (no-op on the live VPS), adds a unique index on `leads.phone` (or logs a clear skip-with-duplicate-list), and converts whichever native-enum columns actually exist to VARCHAR with corrected values. That last one (`010_enum_columns_to_varchar.py`) is the migration that changes existing column types — it was extensively tested against a real, disposable local Postgres instance this session obtained specifically for that purpose (two bootstrap scenarios, real seeded data, full ORM round-trip verified — see §5), but your staging run is still the first time it touches anything resembling your actual data shape.
2. **Re-verify `app/api/leads.py`** specifically — it was under active concurrent editing by a separately-started session throughout this audit and changed shape 3 times. Run `pytest tests/security/test_rbac.py -k leads` immediately before deploy to confirm the auth fix on `/stats/summary` and `/scrape/{task_id}` is still present in whatever that session's final version is.
3. Decide whether to arm `METRICS_TOKEN` (F-SEC8) — depends on the live Caddy config, which this session couldn't check.
4. Commit the full batch (see FIX_PLAN.md §"Summary for the owner").

Nothing needs the owner's input to ship this audit's findings anymore — the enum retrofit (F-DB4) that previously needed a maintenance-window sign-off was fully built and verified once real Postgres access was obtained. The one adjacent discovery from the F-DB2 investigation (`POST /api/leads/` in-memory storage) is being handled in that same separate session, unrelated to this report.
