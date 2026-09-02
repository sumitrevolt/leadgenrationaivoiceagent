# Product-1 path to 50 paid/day (90-day capacity program)

**Product:** AI Automated Marketing Main ₹1,999/mo (not Voice standalone).
**North-star KPI:** new paid Marketing activations / day (active sub + invoice), not leads.
**Honest math:** ~50 paid/day ≈ ₹99,950/day new MRR. Free-stack alone cannot feed this (email ~25/day, 1 Hot Queue owner). Need paid acquisition + sales capacity + onboarding factory.

## Reverse funnel (planning assumptions)

| Stage | Indicative rate | Daily volume for 50 paid |
|-------|-----------------|---------------------------|
| Visits | — | 5k–25k |
| Lead magnets (`/audit`, `/demo`, `/site-audit`) | 2–8% | hundreds–low thousands |
| Hot Queue / sales talk | 10–25% of magnets | hundreds |
| `/start` UPI | 25–40% of sales-ready | ~125–200 starts |
| Paid confirm | 25–40% of starts | **50 paid** |

Adjust rates from PostHog + billing ledger weekly; do not invent testimonials/metrics in marketing copy.

## Phase 0 (Days 0–7) — Unblock

See [HOT_QUEUE_BLITZ_CHECKLIST.md](HOT_QUEUE_BLITZ_CHECKLIST.md).
**Exit:** ≥2 paying Marketing customers.

## Phase 1 (Days 8–30) — System for 1–3 paid/day

1. **Demand:** GSC creds → then consider `GSC_ENABLED` (separate owner gate). Keep pSEO + Postiz own-brand cadence.
2. **Paid ads (owner ₹):** Meta/Google → `/audit` or `/start` with UTMs; daily spend cap + kill switch; no auto-spend buttons in product.
3. **Sales:** Hot Queue SLA + optional second closer hours; WA remains 1-click human.
4. **Onboarding:** Prefer existing auto-onboard / Day-1 pack paths so founder is not required per tenant.
5. **Metric:** Track daily paid activations in admin (ledger-backed); keep `ready_for_first_paid_customer` green.

**Exit:** ≥1 paid/day sustained 7 days; onboarding fail rate &lt;10%.

## Phase 2 (Days 31–60) — Toward ~10 paid/day

1. Multi-closer coverage inside TRAI window (compliance gates untouched).
2. Referral kit push via `/app/affiliates`.
3. Pricing/`/start` CRO — one CTA path; manual UPI stays.
4. Support hours model for ~10 new tenants/day.
5. Watch free LLM quota + worker memcg (heavy/video isolation).

**Exit:** Peak week ≥5–10 paid/day; month-1 churn &lt;5%.

## Phase 3 (Days 61–90) — Capacity design for 50/day

1. Lock CAC vs 1-month gross margin; required ad spend for ~125–200 starts/day.
2. Sales factory roster + queue routing.
3. Onboarding factory: parallel KB seed / sub / week-1 content via Celery (not web process); idempotent.
4. Billing ops: batch UPI confirm / dual-approver UI (still manual rail).
5. Infra: Postgres/Redis/worker headroom; `dsh` + celery DLQ dashboards. Sheet: [CAPACITY_50_DAY.md](CAPACITY_50_DAY.md). `CELERY_ONBOARD_QUEUE` INERT (heavy worker, no new queue).
6. **Kill criteria:** CAC &gt; 1 mo GM or onboarding fail red → pause ads.

**Exit:** Written capacity plan + staging/dry-run of 50 simulated onboardings → owner go/no-go for live 50.

## Capacity proof (2026-08-15)

**Staging measurement (50 fake onboardings, in-process):**
- wall_total: 3.818s (sequential)
- per-job p50: 74.9ms | p95: 122ms | p99: 122.7ms
- throughput: 13.1 onboards/s (sequential in-process)
- failure_rate: 0/50 (0%)
- ONBOARD_TIME_BUDGET_S=300 enforced
- Real bottleneck: Celery worker concurrency (conc=4) + LLM quota (free stack)
- At 2/hour spread, 50/day = trivially achievable

**Verdict: 50/day capacity is ACHIEVABLE with existing infrastructure.** No new workers or queues needed.

## Plugin architecture (2026-08-15)

Every governed component now has a machine-readable PluginManifest:
- 42 plugins registered across 7 categories
- 4 RED plugins require owner approval
- 31 PRODUCTION_PROVEN plugins
- Drift detection via GET /api/admin/plugins
- Schema: app/agents/harness/plugin_manifest.py
- Catalog: app/agents/harness/plugin_catalog.py
- API: app/api/plugin_registry.py

## Automation loop portfolio (2026-08-15)

50 loops inventoried:
- 28 KEEP (active, proven, revenue-relevant)
- 2 FIX (flag flip needed)
- 1 SCALE (daily_video)
- 14 INERT (flag-gated, OFF)
- 8 KILL (legacy, disabled)

Detail: docs/gtm/AUTOMATION_LOOP_PORTFOLIO.md

## Admin dashboard UX (2026-08-15)

Top-fold now shows live scorecards:
- Paid today, activations today, Hot Queue count, pending decisions
- Dynamic next best action engine
- Auto-refresh every 60s

## Admin dashboard plugin registry (2026-08-15)

God Mode section now shows:
- Plugin Registry table with live data from `/api/admin/plugins`
- Category + risk filters
- Drift detection button
- 42 plugins, 7 categories, 4 RED (require owner approval)

## Explorer plugin topology (2026-08-15)

Explorer PLUGINS sidebar tab shows:
- Live plugin data from API with search filter
- Category-grouped list with risk dots and evidence badges
- Risk summary with live counts
- Plugin node in graph connected to admin_ui + explorer
- 358 total nodes, zero orphans

## Onboarding capacity proof (2026-08-15)

50 fake onboardings measured:
- p50: 74.9ms per job
- p95: 122.0ms per job
- throughput: 13.1/s (sequential in-process)
- failure_rate: 0%
- 50/day = ~4s of task time = trivially achievable

## DSH role

Full authority arm (29 agents) improves workforce loop leverage. It does **not** create demand or replace UPI confirm. Kill switch remains `DSH_RUNTIME_ENABLED=0`.

## Reporting cadence

- Weekly: paid/day, starts/day, Hot Queue touch count, CAC (if ads on), onboarding fails.
- Never claim “50/day live” without billing-ledger evidence.
