# Inbound Request Guard — Research & Integration

**Date:** 2026-06-15 · **Scope:** One more broader SOTA pass; add the genuinely-missing inbound reliability primitive.
**Outcome:** `RequestGuardMiddleware` — per-request **timeout (504)** + per-worker **load-shed (503)**. GATED `REQUEST_GUARD` (default OFF = zero change). prod_check green.

---

## 1. Gap (proven)

Audit ne external-call timeouts cover kiye the (free_ai chain). Par **inbound side** unprotected tha:
- Middleware stack (`setup_middleware`): gzip · TenantContext · TenantBranding · RateLimit (per-IP) · RequestTracing · SecurityHeaders. **Koi per-request timeout NAHI, koi load-shed/concurrency-cap NAHI** (grep-confirmed: zero `wait_for`/`Semaphore`/`503`/`concurrency`).
- uvicorn directly chalta (gunicorn nahi) → **koi per-request worker timeout nahi**. Matlab ek slow/hung handler ek worker ko **indefinitely hold** kar sakta (WEB_CONCURRENCY=2 pe = aadha capacity gone); overload pe queue unbounded → collapse.

Yeh classic backend-reliability gap hai (persona principle: timeouts everywhere + backpressure + load-shedding). External calls pe to tha, inbound pe nahi tha.

## 2. Fix — RequestGuardMiddleware (`app/middleware/__init__.py`)

- **Per-request timeout** → slow handler `asyncio.wait_for(timeout)` ke baad **504** (upstream-proxy 504 se pehle, clean). Default `REQUEST_TIMEOUT_S=55`.
- **Load-shed** → per-worker in-flight `> REQUEST_MAX_INFLIGHT` (default 200) pe naye request ko **503 + Retry-After** (running requests cut NAHI hote — door-level shedding, overload-collapse se bachao). Per-worker granularity = sahi (har worker apna event-loop protect kare).
- **Path-aware skip** (`REQUEST_GUARD_SKIP`): `/ws` (voice WebSocket), `/api/web-call`, `/api/voiceai`, `/agents/coordinate*`, `/api/ml`, `/api/ai`, `/health`, `/metrics`, + koi bhi `stream` path — warna long-running voice/LLM/SSE galti se cut ho jaate. (WebSocket waise bhi BaseHTTPMiddleware se exempt.)
- **GATED `REQUEST_GUARD=1`** — default OFF = **zero behaviour change**. Added LAST in chain = executes FIRST (outermost) → guard poore request ko wrap karta.
- **FAIL-OPEN + never-raise** — guard ki koi bhi internal error pe request normally process hoti (legit traffic kabhi na ruke).

## 3. Discipline — kya skip kiya (duplicate/over-engineering nahi)

- **Native ASGI middleware** (1.8x faster) ke bajaye `BaseHTTPMiddleware` use kiya — tere existing stack ke consistent + gated-OFF hai to perf-impact nahi. (Future: pure-ASGI me port kar sakte agar hot-path pe daala.)
- **Distributed/global concurrency cap** nahi — per-worker hi sahi hai (worker apna loop protect kare; global coordination ki Redis-latency nahi chahiye).
- **PII log-redaction / SLO burn-rate alerts** — noted as next candidates, par yeh turn ek focused reliability primitive pe rakha.

## 4. Verification + rollout

`python scripts/prod_check.py` → **ALL CHECKS PASSED**, `app.main` imports OK, routes 652 (no endpoint — pure middleware), guard OFF (no change). Free-stack (pure asyncio), no new dep.

**Safe rollout:** deploy with `REQUEST_GUARD=0` (no-op) → staging/low-traffic pe `REQUEST_GUARD=1` set + load-test (legit slow endpoints skip-list me hain confirm karo, 504/503 logs Loki me dekho) → tune `REQUEST_TIMEOUT_S`/`REQUEST_MAX_INFLIGHT` → prod ON. Instant rollback = `REQUEST_GUARD=0` + restart.

### Files
- `app/middleware/__init__.py` (RequestGuardMiddleware + gated registration)
- `.env.example` (REQUEST_GUARD + tunables documented)

## Sources
- FastAPI global request timeout — https://github.com/fastapi/fastapi/discussions/7364
- FastAPI middleware performance (native ASGI vs BaseHTTPMiddleware) — https://medium.com/@dikhyantkrishnadalai/fastapi-performance-bottlenecks-why-middleware-and-orms-kill-throughput-and-how-to-fix-them-a79924bfaebb
- Background jobs / backpressure 2026 — https://www.digitalapplied.com/blog/background-job-queue-patterns-2026-engineering-reference
