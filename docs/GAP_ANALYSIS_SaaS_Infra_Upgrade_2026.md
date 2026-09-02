# Gap Analysis + Plan — SaaS Infra Upgrade (Production-Grade Patterns)

> Date: 2026-06-16 · Source design doc: "SaaS Infrastructure Upgrade (Production-Grade Patterns)"
> Scope (user-chosen): Postgres RLS · Per-tenant Feature Flags · System-wide Circuit Breaker · Per-tenant Health Metrics
> Verdict: design solid hai, par codebase me kuch already-built hai (overlap), aur **2 critical correctness/security gotchas** hain jo plan ko badalte hain. OpenAPI item ~free (already-there).

---

## 1. TL;DR — verdict matrix

| Component | Abhi kya hai | Gap (naya kaam) | Risk | Effort |
|---|---|---|---|---|
| **Postgres RLS** | Kuch nahi — sirf app-level manual `.where(client_id==...)` | DB-enforced isolation | 🔴 HIGH (superuser-bypass + spoofable tenant_id) | L |
| **Per-tenant Feature Flags** | Static env-flag list (`AUTOMATION_FLAGS`, global on/off) | Redis per-tenant/percentage store | 🟢 LOW (isolated, additive) | S–M |
| **Circuit Breaker (all APIs)** | LLM-only inline breaker (`free_ai.py`) | Reusable breaker for Vobiz/SMTP/Maps/Pollinations/Razorpay | 🟡 MED | M |
| **Per-tenant Health Metrics** | `client_health.py` (business churn score, alag axis) + `llm_metrics.py` (pattern) | Per-tenant request latency/error-rate | 🟢 LOW–MED | S–M |
| OpenAPI (deprioritized) | FastAPI native `/openapi.json` + `/docs` already-live | ~0 (sirf tags/examples) | — | XS |

**Common ethos fit:** chaaron easily flag-gated + fail-open + additive ban sakte — project ke baaki patterns jaise. Recommend flags: `RLS_ENABLED`, `FEATURE_FLAGS`, `CIRCUIT_BREAKERS`, `TENANT_HEALTH` (sab default OFF).

---

## 2. 🚨 Critical findings (yeh plan badalte — pehle padho)

### 2.1 RLS silently bypass ho jaayega (superuser trap)
App `DATABASE_URL` me **`POSTGRES_USER=leadgen`** se connect karta (`docker-compose.vps.yml`). Official `postgres` image me `POSTGRES_USER` = **superuser**. Postgres me **superuser AUR table-owner RLS ko bypass karte hain — `FORCE ROW LEVEL SECURITY` ke baad bhi superuser bypass karta.**

➡️ Agar naive `ENABLE ROW LEVEL SECURITY` laga diya, **policies chup-chaap no-op** rahengi — aur humein lagega isolation on hai (false security = worst outcome).

**Fix (Phase 0, mandatory):** ek dedicated **non-superuser, non-owner** role banao:
```sql
CREATE ROLE leadgen_app LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE leadgen TO leadgen_app;
GRANT USAGE ON SCHEMA public TO leadgen_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO leadgen_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO leadgen_app;
```
Web app (request path) → `leadgen_app`. Migrations/`create_all`/cross-tenant background jobs → owner `leadgen` (RLS bypass intentional). Iska matlab **do DATABASE_URLs** (ya do engines): `DATABASE_URL_APP` (RLS-bound) + `DATABASE_URL` (owner, worker/alembic).

### 2.2 tenant_id abhi SPOOFABLE header se aata hai
`TenantContextMiddleware` (`app/middleware/__init__.py:334`) `request.state.tenant_id` ko seedhe **`X-Tenant-ID` header** se set karta — koi auth-validation nahi. RLS isi value pe chalega. **Agar attacker apna header bhejke kisi aur ka tenant_id daal de → poora dusra tenant ka data.** (Plus subdomain check `"subdomain" in request.url.netloc` literally buggy hai — substring "subdomain" dhoondhta.)

➡️ **RLS se PEHLE:** tenant/client_id authenticated session/JWT se derive karo (login → client), header se nahi. Header sirf admin/impersonation (audited) ke liye. Yeh #1 correctness point hai — iske bina RLS = jhoothi suraksha.

### 2.3 LLM breaker ko mat chhedo (abhi)
`free_ai.py` ka breaker domain-tuned hai (per-provider escalating 60s→30min, "TPD/per day" → seedha 30min, multi-key rotation). Naya generic breaker sirf **baaki externals** (Vobiz/SMTP/Maps/Pollinations/Razorpay) pe lagao. LLM ko baad me (optional) refactor karna — abhi additive-only, low-risk.

### 2.4 Memory drift (bonus catch)
`CLAUDE.md` keh raha `PlanTierRateLimitMiddleware` `middleware/__init__.py` me ADDED hai — **source me nahi hai** (sirf stale `graphify-out/` cache me). Ya revert hua ya commit nahi hua. Reconcile karo.

---

## 3. Per-component gap + plan

### 3.1 Postgres RLS — genuinely naya, highest value, highest risk

**Tenant column reality:** dominant key = **`client_id`** (`String(36)` FK → `clients.id`) in `billing_record, call_log, campaign, data_credits(×4), payment(×5), user`. `agent` me `current_client_id`. `clients` table = tenant root. Design ka `client_id`/`tenant_id`/`user_id` scan sahi hai — par primary `client_id` rakho.

**De-risked points (achhi khabar):**
- **PgBouncer = session mode** (`docker-compose.vps.yml` confirmed) → `SET LOCAL app.current_tenant` transaction-scoped, RLS-safe. (Agar future me transaction mode kiya: `SET LOCAL` phir bhi safe; plain `SET` toot-ta — note rakho.)
- Redis/infra already hai. Naya DB extension nahi chahiye (RLS core Postgres).

**Plan:**
1. **Phase 0 role swap** (§2.1) + tenant_id-from-auth (§2.2). Yeh bina RLS ke bhi deploy ho sakta (no behavior change).
2. **GUC set hook:** `get_async_db` ke transaction ke andar, request ke shuru me:
   ```python
   await session.execute(text("SELECT set_config('app.current_tenant', :cid, true)"), {"cid": tenant_id})
   ```
   ⚠️ Design ka `f"SET LOCAL app.current_tenant = '{tenant_id}'"` = **SQL-injection risk**. `set_config(..., true)` parameterized use karo (`true` = LOCAL/txn-scoped).
3. **Policy generator** (`RLSManager`): `information_schema` scan → har tenant-column table pe `USING` + `WITH CHECK` policy, idempotent (`DROP POLICY IF EXISTS`). Design ka generator pattern sahi.
4. **Background/cross-tenant jobs:** Celery worker, schedulers, aur **`client_health._gather_signals()` jaisa `select(Lead).limit(5000)` across ALL clients** — yeh tenant-context ke bina chalte. Yeh owner role (`leadgen`, RLS-bypass) pe rakho, ya explicit service-context. **Yeh design me missing tha — must handle, warna background jobs RLS se block/khaali ho jaayenge.**
5. **SQLite no-op:** rollback DB SQLite hai — RLS Postgres-only. Dialect detect karke SQLite pe graceful skip (project ethos).
6. **Verification (critical):** staging pe — (a) tenant A ke session me tenant B ka row INVISIBLE (SELECT/UPDATE/DELETE/INSERT-with-wrong-cid sab); (b) owner role abhi sab dekh sakta (jobs OK); (c) `leadgen_app` se cross-tenant query khaali. Yeh test suite ke bina RLS ship MAT karo.

**Flag:** `RLS_ENABLED` (default OFF). OFF = aaj jaisa exact behaviour.

### 3.2 Per-tenant Feature Flags — naya, low risk

**Abhi:** `AUTOMATION_FLAGS` (`growth.py:1070`) = ~80 env-var NAAMON ki static list, `GET /api/growth/infra/flags` pe read-only. Yeh **global env booleans** (`.env` edit + container recreate). Koi per-tenant/percentage/runtime-toggle/storage nahi. **Yeh infra/automation-loop govern karta — ALAG concern. Ise mat merge karo.**

**Naya (design = sound):** Redis-backed `FeatureFlagService` — states `disabled/enabled_all/enabled_percentage/enabled_tenants`, deterministic `hash(tenant_id) % 100 < pct` bucketing, 60s TTL cache. **Reuse `get_redis_client()`** (`app/cache/__init__.py`, InMemoryCache fallback built-in). Admin toggle API + marketing.html me ek "Feature Flags" tab (CLAUDE.md rule: API + UI saath).

**Refinements:** Redis down → InMemoryCache fallback per-worker inconsistent ho sakta — default-OFF semantics ke saath yeh acceptable (fail-safe). Flag-key namespace: `feature_flag:{key}`. Product/customer-facing features ke liye, infra ke liye nahi (boundary doc me likho).

**Flag:** `FEATURE_FLAGS` (default OFF).

### 3.3 System-wide Circuit Breaker — naya wrapper, proven semantics reuse

**Abhi:** sirf LLM (`free_ai.py` inline, in-process dict, escalating backoff). **Baaki externals UNPROTECTED:** Vobiz/Exotel, Hostinger SMTP, Google Maps Places, Pollinations, Razorpay. `RequestGuardMiddleware` (per-request timeout) ek backstop hai par per-service fail-fast/fallback nahi.

**Naya:** reusable async `CircuitBreaker` (Redis distributed state + in-memory fallback) — `CLOSED→OPEN→HALF_OPEN`, `asyncio.wait_for` timeout, optional `fallback`. Pehle in-process version bhi chalega (free_ai jaisa) — distributed Redis state Phase-2.5.

**Refinements:**
- LLM ko abhi mat touch (§2.3). Naya breaker sirf 5 externals pe.
- **Fail-open default:** breaker logic khud error de → call through (project ethos). Razorpay/SMTP pe fallback = "queue/retry later", Maps/Pollinations pe = cached/SVG-poster fallback (jo already partially hai).
- Per-service config (`failure_threshold`, `timeout`, `reset_timeout`) — design ka `CircuitBreakerConfig` theek.

**Flag:** `CIRCUIT_BREAKERS` (default OFF → wrappers pass-through).

### 3.4 Per-tenant Health Metrics — partial overlap, clarify axis

**Abhi (overlap — padho):**
- `app/platform/client_health.py` = per-CLIENT **business** health (churn score: payment/leads/content, 0-100). Yeh **retention axis hai, infra nahi.** Confuse mat karo.
- `app/platform/llm_metrics.py` = per-provider request metrics (calls/ok-rate/avg-ms, jsonl). **Yeh PATTERN reuse karo.**
- `tenant_manager.py`, `integration_health.py`, `automation_health.py` exist — naam/dashboard reuse.
- `RequestTracingMiddleware` request-IDs add karta par per-tenant latency/error RECORD nahi karta. **Koi Prometheus `/metrics` with per-request histograms nahi mila.**

**Naya:** `TenantHealthService` — per-tenant request count/success/latency(p95)/error-rate. Middleware hook `request.state.tenant_id` pe (Phase 0 ke baad jab woh auth-derived hai). `llm_metrics.py` ka lightweight jsonl-or-Redis-rolling-counter pattern follow. Admin endpoint + UI tab. **Naam `tenant_request_health` rakho** taaki `client_health` (business) se clearly alag rahe.

**Wire:** `setup_middleware(app, ...)` (`app/main.py:217` se call hota) = sahi injection point.

**Flag:** `TENANT_HEALTH` (default OFF).

---

## 4. Phased roadmap (risk-ordered — RLS sabse aakhri)

| Phase | Kaam | Behavior change | Risk |
|---|---|---|---|
| **0 — Prep** | `leadgen_app` non-superuser role · tenant_id auth-derive (header→session) · `app/infrastructure/` package scaffold · CLAUDE.md PlanTier drift reconcile | None | Low |
| **1 — Feature Flags** | Redis `FeatureFlagService` + admin API + UI tab | None (default OFF) | Low |
| **2 — Circuit Breaker** | Reusable breaker → Vobiz/SMTP/Maps/Pollinations/Razorpay wrappers + fallbacks | None (OFF=pass-through) | Med |
| **3 — Tenant Health** | `TenantHealthService` + middleware hook + admin dashboard | None (OFF) | Low–Med |
| **4 — RLS (staging-first)** | Policy generator · `set_config` GUC hook · worker owner-role bypass · full isolation test-suite · staged enable | DB-enforced (gated) | High |

Har phase: alag deploy, alag flag, prod-check + targeted pytest (`scripts\run_tests.bat`, log Read), staging verify (RLS pe mandatory).

---

## 5. Tests + flags to add

**New test files (extend existing `tests/test_phase3_billing_tenant.py`):**
- `test_feature_flags.py` — state eval (disabled/all/percentage/tenants), deterministic bucketing, Redis-down default-off.
- `test_circuit_breaker.py` — CLOSED→OPEN threshold, HALF_OPEN recovery, fallback, fail-open on breaker error.
- `test_rls_isolation.py` — **(staging/CI Postgres req'd)** tenant A ≠ tenant B visibility; owner role full access; `leadgen_app` cross-tenant empty.
- `test_tenant_health.py` — record/aggregate, p95, no-tenant skip.

**Flags:** `RLS_ENABLED`, `FEATURE_FLAGS`, `CIRCUIT_BREAKERS`, `TENANT_HEALTH` → `AUTOMATION_FLAGS` list (`growth.py`) me add (registry).

**Files (proposed):** `app/infrastructure/feature_flags.py`, `circuit_breaker.py`, `rls_manager.py`, `tenant_health.py` + `app/infrastructure/__init__.py`. (Design ka `app/infrastructure/` layout — repo me abhi nahi hai, naya banega.)

---

## 6. OpenAPI (5th item, deprioritized)
FastAPI already `/openapi.json` + `/docs` (Swagger) + `/redoc` deta hai — **already-live, ~0 effort.** Sirf optional polish: route `tags`, response `examples`, aur prod me `/docs` expose karna hai ya admin-gate — decide karna. Naya code lagभग nahi.

---

## 7. Bottom line
- **2 genuinely naye high-value:** Postgres RLS (DB-enforced isolation) + Redis per-tenant feature flags.
- **2 worthwhile extensions:** circuit breaker (non-LLM externals) + per-tenant request-health (vs existing business-health).
- **Blockers before RLS:** non-superuser role + auth-derived tenant_id (security-critical). Inke bina RLS = jhoothi isolation.
- **OpenAPI:** practically already done.
- Sab project ke flag-gated/fail-open/additive ethos me fit. Recommend order: Flags → Breaker → Tenant-Health → RLS (staging-first).
