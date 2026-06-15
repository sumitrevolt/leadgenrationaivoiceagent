# Route Inventory — leadgenrationaivoiceagent (656 routes across 48 files)

Read-only map for the Dimension-4 scope-reduction (target ~400). No routes deleted here.

By method: GET=338, POST=300, DELETE=12, PATCH=4, PUT=2

## Routes per router (largest first)

| Count | File |
|---|---|
| 158 | app/api/growth.py |
| 53 | app/api/marketing.py |
| 52 | app/main.py |
| 31 | app/api/ml_training.py |
| 21 | app/api/billing.py |
| 17 | app/api/platform.py |
| 14 | app/api/data.py |
| 14 | app/api/clientops.py |
| 13 | app/api/widgets.py |
| 13 | app/api/minisite_builder.py |
| 13 | app/api/analytics.py |
| 12 | app/api/lifecycle.py |
| 12 | app/api/contentplus.py |
| 12 | app/api/clientcrm.py |
| 12 | app/api/admin.py |
| 11 | app/api/whatsapp.py |
| 11 | app/api/voiceai.py |
| 11 | app/api/team.py |
| 10 | app/api/seoops.py |
| 10 | app/api/contentauto.py |
| 9 | app/api/niche_db.py |
| 9 | app/api/memory_api.py |
| 9 | app/api/campaigns.py |
| 9 | app/api/brandassets.py |
| 9 | app/api/agents.py |
| 8 | app/api/webhooks.py |
| 8 | app/api/leads.py |
| 8 | app/api/customer_auth.py |
| 7 | app/api/team_access.py |
| 7 | app/api/localseo.py |
| 7 | app/api/journeys.py |
| 7 | app/api/engage.py |
| 7 | app/api/clients.py |
| 7 | app/api/ai.py |
| 6 | app/api/public_site.py |
| 6 | app/api/privacy_ops.py |
| 6 | app/api/health.py |
| 5 | app/api/voice_product.py |
| 4 | app/api/creative.py |
| 3 | app/api/telephony_vobiz.py |
| 3 | app/api/combo_product.py |
| 3 | app/api/booking.py |
| 2 | app/api/events.py |
| 2 | app/api/customer_dashboard.py |
| 2 | app/api/admin_dashboard.py |
| 1 | app/api/web_call.py |
| 1 | app/api/ratelimit.py |
| 1 | app/api/auth_deps.py |

## How to find deletion candidates (do before removing anything)
1. Dead routes: endpoint path not referenced in any frontend/*.html, scheduler, or test. Check: `grep -rn "<path>" frontend/ app/platform/team_scheduler.py tests/`.
2. Duplicates: same resource exposed twice (e.g. a feature re-added — CLAUDE.md notes a festivals/review/ads duplication incident). `grep '@router' app/api/<file>.py`.
3. Demo/experimental: routes only hit by /demo or one-off experiments.
4. Deprecate-behind-flag first, run prod_check.py + run_tests.bat, /ship, verify /health=production, THEN delete — small batches.

## Biggest reduction opportunities (by router size — verify before cutting)
- app/api/growth.py — 158 routes: review for demo/duplicate/never-called endpoints.
- app/api/marketing.py — 53 routes: review for demo/duplicate/never-called endpoints.
- app/api/main.py — 52 routes: review for demo/duplicate/never-called endpoints.
- app/api/ml_training.py — 31 routes: review for demo/duplicate/never-called endpoints.
- app/api/billing.py — 21 routes: review for demo/duplicate/never-called endpoints.
- app/api/platform.py — 17 routes: review for demo/duplicate/never-called endpoints.
- app/api/data.py — 14 routes: review for demo/duplicate/never-called endpoints.
- app/api/clientops.py — 14 routes: review for demo/duplicate/never-called endpoints.
