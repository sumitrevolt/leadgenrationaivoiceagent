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
5. Infra: Postgres/Redis/worker headroom; `dsh` + celery DLQ dashboards.
6. **Kill criteria:** CAC &gt; 1 mo GM or onboarding fail red → pause ads.

**Exit:** Written capacity plan + staging/dry-run of 50 simulated onboardings → owner go/no-go for live 50.

## DSH role

Full authority arm (29 agents) improves workforce loop leverage. It does **not** create demand or replace UPI confirm. Kill switch remains `DSH_RUNTIME_ENABLED=0`.

## Reporting cadence

- Weekly: paid/day, starts/day, Hot Queue touch count, CAC (if ads on), onboarding fails.
- Never claim “50/day live” without billing-ledger evidence.
