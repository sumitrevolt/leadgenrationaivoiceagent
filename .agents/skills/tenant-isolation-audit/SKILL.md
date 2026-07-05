---
name: tenant-isolation-audit
description: Multi-tenant isolation deep-audit — tenant middleware FAIL-OPEN risk, IDOR sweep beyond billing, per-tenant feature flags, plan-tier rate limits, cross-tenant data leaks in KB/Qdrant/exports/webhooks. Use jab naya customer-facing route bane, white-label/tenant feature change ho, ya "customer A ko customer B ka data dikh sakta hai kya" audit chahiye.
---

# Tenant Isolation Audit (ek leak = trust khatam)

> Enterprise audit skill. `leadgen-security-rbac` = broad security lens; **yeh = tenant-boundary MICROSCOPE**. Pehle `context-first`.

## Repo truth
- **Tenant resolve**: `middleware/tenant.py` — subdomain + custom_domain, **FAIL-OPEN by design** (resolve fail = default tenant, availability > isolation). GOTCHA: FAIL-OPEN matlab misconfigured domain kisi aur tenant ke context me land kar sakta — har data-read me EXPLICIT client_id scope chahiye, middleware pe bharosa akela kaafi NAHI.
- **Customer auth**: `_authed_client_id` dep — C1 me har BILLING mutation pe laga. Audit sweep = billing ke BAAHAR bhi (leads read, KB query, exports, webhooks config, mini-site edits, campaign views).
- **Per-tenant flags**: N.2 runtime feature-flags (Redis-backed, master `FEATURE_FLAGS`).
- **Plan-tier rate limit**: `PlanTierRateLimitMiddleware` (Starter 60rpm / Growth 200rpm / Advanced 500rpm), gate `PLAN_RATE_LIMIT=1`.
- **KB namespaces**: Qdrant `kb_main` single collection — isolation SIRF namespace filter (`client:<id>`) se. Missing filter = cross-tenant RAG leak (voice agent dusre client ka data bol dega!).
- **Customer webhooks (H.1)**: per-customer HMAC — event fan-out me client_id filter verify karo.

## Sweep workflow
1. **Route inventory**: `grep -rn "client_id" app/api/ | grep -v _authed_client_id` → har customer-data route jisme authed dep NAHI = suspect list.
2. **Qdrant queries**: `grep -rn "kb_main\|search(" app/ | grep -iv "client:"` — namespace-filter missing paths.
3. **Exports/downloads**: CSV/report endpoints — client scope + signed/expiring URLs?
4. **Webhook fan-out**: event emit points (`lead.created`, `lead.qualified`, `call.completed`) — sirf owner-tenant ke endpoints ko dispatch?
5. **Background jobs**: Celery staff-jobs jo cross-client iterate karte (auto_content, digest) — per-client output per-client store me hi jaye.
6. **Cache keys**: Redis keys me client_id prefix? Shared cache key = poisoning leak.
7. **Tests**: wrong-tenant 403/404 test har suspect route pe (pattern: `test_billing_truth_2026.py` ka authed-client fixture copy karo).

## Enterprise bar
- Har customer-data query me explicit tenant predicate (middleware implicit context NAHI).
- Wrong-tenant access = 404 (existence bhi leak mat karo), 403 nahi.
- New route checklist me tenant-scope line MANDATORY (api-design skill ke saath).
- Rate-limit + quota per tenant enforced (noisy neighbor).

## Output
Suspect-route table (route × auth dep × tenant predicate × test Y/N) · Qdrant/Redis/webhook leak findings · fixes shipped + wrong-tenant tests added · isolation score /100.

## Related repo skills
`leadgen-security-rbac` (broad security) · `backend-rbac` (roles model) · `api-design` (new-route discipline) · `voice-agent-kb` (KB namespaces) · `data-retention-dpdp` (per-tenant delete).
