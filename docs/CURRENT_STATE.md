# Current State - LeadGen AI

> Short current-state handoff for AI sessions. Code remains source of truth; this file is the reasoning/status layer.

## Date
2026-07-09

## Main Business Focus
Product One / AI Automated Marketing customer deliverability. The immediate goal is making real paid customers see clear delivery proof: onboarding, content, approvals, publishing proof, reports, admin cockpit, and automation logs.

## Product One Delivery Audit — Gap-Closing Pass (this session)
A 3-agent parallel audit (file:line precision) verified the actual state of every ADR-064 deliverable against the full "make Product One actually deliverable" spec. Headline finding: ~90% of the gaps were frontend-surfacing/consolidation problems, not missing backend. See `docs/PRODUCT_ONE_DELIVERY_MAP.md` for the full feature-by-feature table (19 rows) — it is now the source of truth for Product One delivery status.

Closed in this session (Phases 2-10, all with passing tests + `prod_check.py` + `check_secrets.py`):
- Admin Delivery Cockpit: fixed a real dead-code bug (`healthBadge()`/`nextAction()` reading a `c.health.*` shape the API never returns), surfaced per-customer content/failure counts, added ₹-priced plan, backfilled a missing scheduler job into the registry.
- Automation Logs: built the missing admin filter panel (was API-only since ADR-064).
- Failed Jobs: new consolidated view (scheduler run-history + DLQ + delivery-log failures).
- Agents visibility: added 7-day success/failure counts; clarified 3 previously-conflated concepts (AI Staff / Multi-Agent Coordination / scheduler registry).
- Admin nav: promoted Agents/Failed Jobs/Plans & Billing out of a collapsed section (11 → 14 core links).
- Customer My Delivery tab: fixed a progress-bar data-binding bug, merged in Home tab's duplicate content, added connected-channels + report summary, consolidated approvals.
- Customer Reports: new IDOR-safe `GET /api/customer/report/branded` makes the previously admin-only white-label monthly report customer-visible (closes the single biggest "customer can't see the benefit" gap found).
- Social Setup Wizard: deduped GBP/FB/Instagram fields across two wizards, unified two approval-preference vocabularies into one, added read-only niche display + 5-item setup checklist.
- Tests: added cross-role negative auth, empty-state, wizard→ledger-event, and DB-backed failed-job tests.

**New finding, flagged not fixed:** a second, unrelated report system (`GET /api/customer/report`, `app.marketing.monthly_report`) was discovered mid-Phase-8 (route-name collision) — also orphaned from any frontend UI. Out of scope for this pass; documented as row 19 in the delivery map.

**Explicitly out of scope this pass (named, not silently dropped):** switching coding-agent models to GLM/Qwen/Kimi (can't switch own inference backend; user's own conclusion deprioritized it); literal cut to exactly 5 customer tabs (Billing/Support/Leads-Inbox are real, kept); PII-masking audit before external LLM calls in the 46 `app/marketing/*.py` modules (confirmed real DPDP-adjacent gap via grep, but a 46-call-site audit is a separate effort).

## Product One Delivery State (pre-existing, still true)
- Customer proof route: `GET /api/customer/delivery-proof`.
- Customer approval routes: `/api/customer/approvals/*`.
- Delivery ledger canonical post events: `post_draft_created`, `post_approved`, `post_published`, `post_failed`.
- Delivery Command Center revenue reads `data.revenue`; `by_plan` shape is `{Plan: {count, mrr}}`.

## Worktree Warning
This session's work is committed... **NOT YET** — see below. Branch `claude/product-one-delivery-audit-b70d9f`, building on ADR-064 (`ecbfc53`). Never use `git add -A`; stage exact files only if the user asks for commit.

## Safety State
- No deploy performed this session.
- No `.env` changes.
- No outbound send/call/post automation enabled.
- Compliance gates unchanged.
- `EMAIL_WARMUP` remains paused.

## Last Verified Gate (this session)
- Full targeted pytest across all touched files: green (product_one_delivery, scheduler_admin, admin_command_center, client_delivery_fields, automation_logs, automation_log_service, customer_dashboard_frontend, customer_delivery_os, customer_deliverable_db, social_setup_wizard, job_run_history, admin_nav_ia_cleanup, office_hq).
- `ruff check app`: pre-existing 59 findings confirmed NOT in any file this session touched (verified by filename grep against the ruff output).
- `check_secrets.py`: clean.
- `prod_check.py`: PASS (route dupes 0, wiring gaps 0 — caught and fixed one real duplicate route during this session: a new customer report endpoint accidentally shadowed a pre-existing `/api/customer/report`, renamed to `/report/branded`).
- Browser-verified (preview tools) the customer dashboard's My Delivery/Home/Setup tabs and admin cockpit — caught and fixed one real runtime bug (`node --check` couldn't catch it: a top-level `var` was unexpectedly unresolved in the browser's execution context; refactored to a self-contained function scope, verified fixed).
- Node `--check` on every touched inline `<script>` block: clean.
