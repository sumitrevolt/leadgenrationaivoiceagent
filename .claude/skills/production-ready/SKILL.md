---
name: production-ready
description: LeadGen production readiness gate — live activation summary, prod_check, cross-path audit, Product-1 vs Product-2 GO status, optional hardening. Use when user asks production ready, go-live, launch, readiness audit, or before declaring platform sellable.
---

# Production Ready — LeadGen AI (2026-06-21 truth)

**Verdict:** Product-1 (Marketing) = **GO**. Product-2 (Voice standalone) = code GO, **commercial blocked** (Vobiz/DLT).

Full audit: `docs/PRODUCTION_READINESS_AUDIT_2026_06_21.md`

## Live probes (no auth)

```powershell
curl.exe -fsS https://leadsgenai.in/health
curl.exe -fsS https://leadsgenai.in/api/activation/summary
```

Expect:
- `/health` → `environment: production`, `status: healthy`
- `/api/activation/summary` → `ready_for_first_paid_customer: true`, `blocker_count: 0`

WARN only (not GO blockers): `sentry`, `turnstile` — optional hardening.

## Windows verify suite (engineering gate)

Order:
1. `.venv\Scripts\python.exe scripts\prod_check.py` — ALL PASSED
2. `.venv\Scripts\python.exe scripts\explorer_sync.py --check` — 0 orphans
3. `.venv\Scripts\python.exe scripts\cross_path_audit.py` — OK
4. `.venv\Scripts\python.exe scripts\check_secrets.py`
5. Targeted pytest: `test_2026_features`, `test_cross_path_telephony`, `test_explorer_sync`

`quick` = steps 1+2 only.

## Product split GO matrix

| | Marketing (P1) | Voice Agent (P2) |
|--|----------------|------------------|
| Sell now? | ✅ | ❌ cold-call |
| Payments | UPI armed (`UPI_VPA` / admin config) | Same billing path |
| DLT needed? | No (inbound/callback OK later) | Yes outbound |
| Test free | `/app/marketing`, `/audit` | `/app/test-call` web-call |
| Blocker | None (sales) | Vobiz recharge + DID + DLT |

ADR: `product-split-adr` skill — bundle framing mat use.

## Optional hardening (WARN → OK)

| Item | Action |
|------|--------|
| Sentry | `SENTRY_DSN` + `ENVIRONMENT=production` in VPS `.env` |
| Turnstile | `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET_KEY` |
| Revenue trends | `REVENUE_TRENDS=1` or `scripts/vps_enable_readiness_flags.py` on VPS |
| Plan rate limit | `PLAN_RATE_LIMIT=1` |

VPS script (safe flags, no creds): `python3 /opt/leadgen/scripts/vps_enable_readiness_flags.py`

## Deploy after code change

`verify-ship` → `leadgen-ops` → Docker `build app` + `up -d --no-deps app`

## Don't rebuild for "readiness"

Infra saturated (CI, Celery, obs stack, activation API) — gap = **activation creds** or **voice commercial**, not new code.

## Council for ambiguous launch decisions

`llm-council-decision` or `POST /api/agents/council` (admin)
