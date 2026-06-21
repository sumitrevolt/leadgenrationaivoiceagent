---
name: duplicate-route-guard
description: Prevent FastAPI duplicate routes (first-route-wins shadow). Grep all routers before adding marketing/growth/voice API routes. Use on every new @router or @app.get endpoint.
---
# Duplicate Route Guard

**Gotcha:** FastAPI **first route wins** — duplicate `@router` silently shadows later handler → prod 404/wrong behavior.

## Before ANY new route

```bash
# Marketing (split godfiles — sab grep karo)
rg "@router\.(get|post|put|delete|patch)" app/api/marketing.py app/api/marketing_tools.py app/api/marketing_models.py

# Growth split
rg "@router" app/api/growth.py app/api/growth_revenue.py app/api/growth_crm.py app/api/growth_deliverability.py app/api/growth_feature_flags.py app/api/growth_prospects.py app/api/growth_process.py app/api/growth_content.py app/api/growth_automation.py

# Voice / public
rg "@router" app/api/voice_product.py app/api/web_call.py app/api/voiceai.py
rg "@app\.(get|post)" app/main.py
```

Search **exact path string** too: `rg '"/your-path"' app/`

## Page routes (`@app.get`)

Naye `/app/*` pages = Docker **rebuild** + curl verify (stale .pyc lesson).

## Fix pattern

- Extend existing handler OR rename path — **never** duplicate decorator
- Refactor 2026-06-20: routes split across modules — grep **all** siblings

## Verify

`scripts/prod_check.py` route count · manual curl new endpoint · OpenAPI duplicate path check
