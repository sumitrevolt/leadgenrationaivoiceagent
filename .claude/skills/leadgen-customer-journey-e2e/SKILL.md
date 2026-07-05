---
name: leadgen-customer-journey-e2e
description: Pura P1 customer journey end-to-end validate karo — jaise ek paying customer. Use jab landing/pricing/signup/UPI-payment/admin-approval/onboarding/portal/content-gen/lead-capture/CRM follow-up ya route-smoke coverage test karna ho.
---

# LeadGen Customer Journey E2E

> Enterprise audit skill. Project ko ek PAYING customer ki tarah test karo. Journey tabhi "works" jab naya business pay→activate→onboard→useful output paaye. Pehle `context-first`.

## Mission
Click-through reality check. Buttons real endpoint pe submit karein, auth-redirect sahi page laaye, forms persist karein, paid-only features server-side gated hon.

## Required flow (exact repo routes)
`/` → `/pricing` → `/start` (signup) → UPI instructions (`/api/public/pay-info`) → admin approval → onboarding (`AUTO_ONBOARD=1`) → `/app/login` → `/app/customer` portal → content generation (`auto_content.py`) → lead capture (`/b/{slug}` mini-site inquiry → `lead.created`) → CRM/cadence follow-up.

Public lead-magnet pages bhi cover karo: `/audit` (#1), `/site-audit` (#2, SSRF-guarded), `/demo`, `/compare`, `/blog`, `/b/{slug}`.

## Workflow
1. Public routes/templates/forms/APIs/redirects/auth-gates/plan-gates discover karo (`grep '@app.get'` + `@router`).
2. P1 pages + critical APIs ka route-smoke (`scripts/check_route.py`; prod_check route-count match).
3. Test customer + test niche se pura P1 flow chalao.
4. Failures ke logs/responses record karo.
5. Har fixed route/form/redirect/gate pe test add.

## Enterprise checks
- Naya `@app.get` page-route → image REBUILD + recreate (`build app` + `up -d --no-deps app`) zaroori; post-deploy curl-verify 200 (stale-.pyc Docker me moot; 2026-07-05). Diagnostic `scripts/check_route.py`.
- Buttons → real endpoints; auth-redirect correct page; forms validate+persist.
- Paid-only features server-side gated (`_authed_client_id` dep).
- Empty / loading / error states visible.
- Demo/seed data real customer se hidden ya labeled.

## Output
Journey pass/fail table · broken route/form list (evidence) · E2E test plan + commands · minimum fix-set for sellable P1 demo · readiness /100.

## Related repo skills (duplicate mat banao)
`onboarding` + `fde-onboard` (activation depth) · `signup` (signup flow) · `verify-ship` (prod_check + deploy gate) · `duplicate-route-guard` · `leadgen-revenue-readiness` (business-impact ranking) · `leadgen-test-guardian` (route-smoke tests).
