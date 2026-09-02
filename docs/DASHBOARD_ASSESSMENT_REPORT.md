# Dashboard Assessment Report (Lean)

**Generated:** 2026-06-26 · **Tool:** `scripts/dashboard_audit.py` (single-file static heuristic scan)

> **Why lean, not the framework:** the design doc proposed 7 Python modules + parser + regression-detector + CI to audit two static HTML files. That is over-engineered for files that change rarely, and LeadGen AI already hand-writes gap docs effectively. This script is the pragmatic substitute. **Caveat:** heuristics detect *presence* of patterns, not runtime correctness — treat as a checklist.

## Scoreboard

| Dashboard | Size | Sections | Charts | Tables | UX heuristics |
| --- | --- | --- | --- | --- | --- |
| Customer | 122.3 KB | 0 | 4 | 3 | 8/8 (100%) |
| Admin | 180.9 KB | 23 | 8 | 6 | 8/8 (100%) |


## Customer Dashboard

**Inventory**

| Metric | Count |
| --- | --- |
| File size | 122.3 KB |
| Sections | 0 |
| KPI / stat cards | 9 |
| Charts (Chart.js/canvas) | 4 |
| Tables | 3 |
| Buttons | 50 |
| Form inputs | 18 |
| Distinct /api endpoints | 27 |


**UX heuristics**

| Check | Present? |
| --- | --- |
| Loading states | ✅ |
| Empty states | ✅ |
| Error handling | ✅ |
| Action feedback (toast) | ✅ |
| ARIA / screen-reader | ✅ |
| Responsive (@media/viewport) | ✅ |
| Keyboard focus | ✅ |
| Semantic landmarks | ✅ |


**Discovered API endpoints**

- /api/billing/invoices
- /api/billing/portal
- /api/billing/subscription
- /api/billing/subscription/cancel
- /api/billing/subscription/pause
- /api/billing/subscription/resume
- /api/billing/usage
- /api/customer/2fa/confirm
- /api/customer/2fa/disable
- /api/customer/2fa/enroll
- /api/customer/2fa/status
- /api/customer/approvals/
- /api/customer/approvals/pending
- /api/customer/auth/me
- /api/customer/auth/portal/content
- /api/customer/branded-feed
- /api/customer/dashboard
- /api/customer/dashboard/send-to-crm
- /api/customer/flow-templates
- /api/customer/leads/
- /api/customer/routing
- /api/customer/speed-to-lead
- /api/customer/webhooks
- /api/customer/webhooks/
- /api/customer/webhooks/_meta
- /api/public/pay-info
- /api/upi/submit

## Admin Dashboard

**Inventory**

| Metric | Count |
| --- | --- |
| File size | 180.9 KB |
| Sections | 23 |
| KPI / stat cards | 8 |
| Charts (Chart.js/canvas) | 8 |
| Tables | 6 |
| Buttons | 88 |
| Form inputs | 35 |
| Distinct /api endpoints | 87 |


**UX heuristics**

| Check | Present? |
| --- | --- |
| Loading states | ✅ |
| Empty states | ✅ |
| Error handling | ✅ |
| Action feedback (toast) | ✅ |
| ARIA / screen-reader | ✅ |
| Responsive (@media/viewport) | ✅ |
| Keyboard focus | ✅ |
| Semantic landmarks | ✅ |


**Discovered API endpoints**

- /api/admin/activity-feed
- /api/admin/agents
- /api/admin/audit-logs
- /api/admin/auth/logout
- /api/admin/call-recordings
- /api/admin/call-recordings/
- /api/admin/campaign/launch
- /api/admin/campaign/status
- /api/admin/campaign/stop
- /api/admin/clients/
- /api/admin/clients/bulk-email
- /api/admin/clients/dedupe
- /api/admin/customers/onboard
- /api/admin/dashboard
- /api/admin/flow/seed-templates
- /api/admin/hourly-activity
- /api/admin/me
- /api/admin/ops/celery-trim
- /api/admin/prospects-preview
- /api/admin/revenue-analytics
- /api/admin/revenue-trend
- /api/admin/sync-health
- /api/admin/system-health-detail
- /api/admin/system/summary
- /api/admin/trust/configure-posthog
- /api/admin/trust/configure-sentry
- /api/admin/trust/configure-turnstile
- /api/admin/upi/activate
- /api/admin/upi/clients
- /api/admin/upi/configure
- /api/admin/web-calls
- /api/assessment/run
- /api/assessment/scores
- /api/billing/invoices
- /api/billing/portal
- /api/billing/subscription
- /api/billing/subscription/
- /api/billing/subscription/cancel
- /api/billing/subscription/pause
- /api/billing/subscription/resume
- /api/billing/usage
- /api/brand/frames/daily
- /api/clientops/approvals
- /api/clientops/approvals/
- /api/clientops/routing
- /api/clients
- /api/data/niches
- /api/growth/cadence/run
- /api/growth/deliverability/summary
- /api/growth/harvest/run
- /api/growth/identity/backfill
- /api/growth/identity/duplicates
- /api/growth/infra/automation-health
- /api/growth/infra/dlq/sweep
- /api/growth/infra/flags
- /api/growth/infra/judge-calibration
- /api/growth/infra/llm
- /api/growth/infra/rag-retrieval-ab
- /api/growth/niche/scrape
- /api/growth/optimizer/run
- /api/growth/overview/today
- /api/growth/process/run/
- /api/growth/process/runs
- /api/growth/revenue/digest/run
- /api/growth/revenue/dunning/run
- /api/growth/revenue/health/run
- /api/growth/revenue/lifecycle/run
- /api/growth/reviews/monitor-run
- /api/growth/sales/team-run
- /api/growth/selfimprove/approval/
- /api/growth/selfimprove/approvals-pending
- /api/growth/selfimprove/run
- /api/growth/selfimprove/status
- /api/growth/selfimprove/task
- /api/growth/speed-to-lead/summary
- /api/growth/upgrader/scan
- /api/journeys/emit
- /api/platform/team
- /api/platform/team/email-followups/run
- /api/platform/team/email-outreach/run
- /api/platform/team/growth/run
- /api/platform/team/prospects/run
- /api/platform/team/reply-triage/run
- /api/platform/team/run/
- /api/platform/team/run/arjun
- /api/platform/team/run/blog
- /api/platform/team/run/isha

## Recommendations (tie to existing backlog)

These map to gaps already tracked in `docs/Competitor_Top20_Feature_Gap_2026.md` — do not spin up new tracking:

1. **Speed-to-lead SLA badge** (P0 #7) — surface inquiry→first-touch time on the customer dashboard ("2-min me jawab"). Marketing gold, infra already exists.
2. **Lead-distribution round-robin** (P0 #10) — admin dashboard view to auto-assign leads to client staff.
3. **AI-search / GEO visibility score** (P1 #11) — new lead-magnet card after audit/site-audit.
4. **UX polish** — address any ⚠️ rows above (loading/empty/error states) before scaling paid signups.

_Report regenerated by re-running `python scripts/dashboard_audit.py`._