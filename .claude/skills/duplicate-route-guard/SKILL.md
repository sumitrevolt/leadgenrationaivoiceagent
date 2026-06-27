---
name: duplicate-route-guard
description: Prevent FastAPI duplicate routes (first-route-wins shadow). Grep all routers before adding marketing/growth/voice API routes. Use on every new @router or @app.get endpoint.
---
# Duplicate Route Guard

**Gotcha:** FastAPI **first route wins** — duplicate `@router` silently shadows later handler → prod 404/wrong behavior.

## Before ANY new route

**Claude:** `context-first` skill — parallel grep batch pehle.

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

## Enterprise gate

Yeh guard = operating loop ka **Discover** phase ka non-negotiable pre-flight (`fable-operating-manual`).

**Change-risk tier:** grep ka *act* Standard, par **blast-radius = jis route ko shadow karoge uska tier**. Billing/`packages.py`-route ya public `/audit`-`/b`-`/start` ya telephony route ko duplicate ne shadow kiya → silent wrong-pricing / 404 / compliance-bypass = **High-risk consequence**. Isliye grep skip karna kabhi "chhota" nahi.

**Evidence (done):** `.venv\Scripts\python.exe scripts\prod_check.py` route count += exactly N (na zyada na kam — zyada = dup, kam = shadow). Naye `@app.get` page-route = container recreate (`up -d --no-deps app`), warna stale .pyc 404.
