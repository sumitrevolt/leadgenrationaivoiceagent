# Scale & Reliability Audit — leadsgenai.in

**Date:** 2026-06-15 · **Auditor:** Backend systems review · **Scope:** Reliability + scalability of the live single-VPS stack
**Method:** Ground-truth code/config read (no theory). Har finding ke saath `file:line` evidence diya hai.

> **STATUS (2026-06-15): P0 + P1 + P2 (safe subset) IMPLEMENTED in repo** (deploy-pending).
> **P0** — `Dockerfile.lock` (proxy-headers), `app/middleware/__init__.py` (XFF), `docker-compose.vps.yml` (redis-cache + noeviction), `app/cache/__init__.py` (cache client + fail-soft), `.env.example`.
> **P1** — `docker-compose.vps.yml` (8 services pe mem/cpu limits, VPS 16GB/4-core), `app/models/base.py` (DB pool 50→10/process), `app/api/health.py` (`/metrics`: LLM provider-health + Celery queue-depth). Detail "P1 implementation notes".
> **P2** — `app/billing/lead_usage.py` (meter-failure observable+recoverable), `app/api/health.py` (`/metrics` CPU non-blocking), `app/main.py` (dev-only reload), `app/models/base.py` (`DB_CREATE_ALL` schema gate). Detail "P2 implementation notes". 2 P2 items DEFERRED-with-rationale (wahi section). Sab backwards-compatible. Deploy + rollback "Deploy handoff" me.

---

## TL;DR (verdict)

Foundation **strong hai** — async-clean code (httpx everywhere, sync I/O event-loop pe nahi), durable Celery config, fail-open degradation discipline, baked ML models, real health probes, Prometheus+Alertmanager wired, prod-down lessons code me visible. Yeh ek mature codebase hai.

Lekin **scale pe 2 latent landmines** hain jo aaj low-traffic pe chhupe hain aur **load badhte hi exactly tab fatenge jab tum scale karoge**:

1. **Ek hi Redis** broker + live-call-state + cache + rate-limit sab ke liye, `allkeys-lru` eviction ke saath → memory pressure pe **queued Celery tasks aur live call-state silently evict** ho sakte (no error, just loss).
2. **Global rate-limiter proxy-IP pe key karta hai** (uvicorn me `--proxy-headers` nahi) → poori site ek hi `100/min + 2000/hr` bucket share karti → **hardware chahe kitna bhi ho, throughput yahीं capped**.

Dono ka fix chhota hai (~1 din total). Inke bina horizontal scaling ka koi matlab nahi — bottleneck hardware me nahi, in 2 jagah hai.

---

## Scorecard

| Dimension | Grade | One-line |
|---|---|---|
| Code-level async hygiene | **A** | httpx async, ML off-loop, sync-DB routes me nahi |
| Fault tolerance (app) | **B+** | Circuit-breaker + fail-open solid; state per-process |
| Data/state durability | **C** | Redis eviction broker/call-state ko risk me daalti |
| Horizontal scalability | **C-** | Rate-limit global-IP cap + over-sized DB pools |
| Resource isolation | **C** | Single VPS, **zero container mem/cpu limits** |
| Observability | **B-** | Stack wired, par RED metrics + LLM-health export missing, traces unwired |
| Ops readiness | **B** | Health probes, self-heal, backups; schema-mgmt drift |

---

## P0 — Fix before any scale-up / first paid load

### P0-1 · Single Redis with `allkeys-lru` = silent task & call-state loss
**Evidence:** `docker-compose.vps.yml:155-156` (`--maxmemory 512mb`, `--maxmemory-policy allkeys-lru`); broker+backend = same instance `app/worker.py:19-21` (`broker=settings.redis_url`); cache/rate-limit/lock/call-state sab `redis://redis:6379/0` (`docker-compose.vps.yml:56`, `app/cache/__init__.py:28-33`).

**Problem:** Ek hi Redis instance, ek hi logical DB (`/0`), 512MB cap, `allkeys-lru` policy. Yeh Redis simultaneously:
- Celery **broker** (queued tasks) + **result backend**
- **DLQ** (`dlq:failed_tasks`, `worker.py:176`)
- **Distributed call-state** (live phone/web calls)
- **Rate-limit** counters + **distributed locks** + **Cache**

`allkeys-lru` ka matlab: memory full hote hi Redis **kisi bhi key** ko evict karega — including queued Celery tasks aur live call-state. Celery + Redis broker pe eviction policy = **upstream-documented data-loss bug** (broker Redis hamesha `noeviction` hona chahiye). Aaj 512MB shayad bharti nahi, isliye chhupa hai — par traffic/cache badhte hi yeh **bina error ke** tasks aur calls khaa jayega.

**Fix (do-step):**
- **Quick (1 line, aaj):** broker Redis ko `--maxmemory-policy noeviction` karo. Cache keys pe already TTL hai (`Cache default_ttl=300`), to woh khud expire honge; broker/lock keys (no TTL) kabhi evict nahi honge. Saath me `Cache.set()` ko fail-soft wrap karo (OOM pe write-fail = cache-miss, raise nahi).
- **Proper (~half day):** alag `redis-cache` container (apna `allkeys-lru` + maxmemory) sirf `Cache` class ke liye (`CACHE_REDIS_URL`); existing Redis `noeviction` pe broker+call-state+rate-limit+DLQ ke liye reserved. Roles physically alag = eviction kabhi critical state ko touch nahi karti.

**Effort:** Quick 30 min · Proper 0.5 din. **Impact:** Eliminates silent task/call loss at scale.

---

### P0-2 · Global rate-limiter proxy-IP pe — poori site ek bucket me
**Evidence:** `app/middleware/__init__.py:193` (`client_ip = request.client.host`); uvicorn CMD me proxy-headers nahi — `Dockerfile.lock:72` (`uvicorn ... --workers ... --timeout-keep-alive 30`); repo-wide `--proxy-headers`/`forwarded-allow-ips` ka **zero** match.

**Problem:** App Caddy ke peeche hai (`127.0.0.1:8000`). Bina `--proxy-headers` ke, `request.client.host` = Docker gateway/Caddy ka IP — **sabhi external users ke liye ek hi constant IP**. `RateLimitMiddleware` (production pe active, `middleware/__init__.py:373-378`) us constant IP pe `100/min + 2000/hr` cap lagati. Matlab:
- **Poora platform collectively ~33 req/min pe throttled** (2000/hr / 60). Thode dashboard users (har page XHR-heavy) milke 429 trip kar denge — **VPS chahe khali ho**.
- Per-IP abuse protection bhi dead (sab ek bucket, attacker bhi legit users ke saath).

Note: dependency-based limiter (`app/api/ratelimit.py:31-39`) XFF **sahi** padhta hai — inconsistency confirm karta ki middleware galat hai.

**Fix:** uvicorn CMD me `--proxy-headers --forwarded-allow-ips="*"` add karo (safe: container port sirf `127.0.0.1` pe bound, sirf local Caddy pahunchta). Isse `request.client.host` = asli client IP ho jayega — middleware **aur** dependency limiter dono consistent. Defensively `RateLimitMiddleware._client_ip` me bhi XFF-first karo. Phir global cap (100/min) re-evaluate karo — authed dashboard API ke liye higher limit ya path-exempt.

**Effort:** 1 line + redeploy. **Impact:** Throughput ceiling hata, real per-IP protection wapas. **Verify:** do alag `X-Forwarded-For` se hit karo — counters alag hone chahiye.

---

## P1 — Fix in the next 1–2 weeks

### P1-1 · Zero container resource limits on a shared single VPS
**Evidence:** `docker-compose.vps.yml` me koi `mem_limit`/`cpus`/`deploy.resources` nahi (grep-confirmed). 13+ containers ek box pe.

**Problem:** Koi bhi ek container (ML load spike, memory leak, runaway job) saara RAM khaa ke **Postgres/Redis ko OOM-kill** kar sakta — cascading outage. Celery me `worker_max_memory_per_child=512MB` hai (`worker.py:100`) par woh **per-child** hai, container-level cap nahi.

**Fix:** Har service pe caps lagao, actual VPS RAM ke hisaab se (`free -h` dekho). Template (Compose v2 non-swarm):
```yaml
app:        { mem_limit: 1500m, cpus: "1.5" }
db:         { mem_limit: 1g,    cpus: "1.0" }   # shared_buffers 256m ke saath consistent
redis:      { mem_limit: 700m }                  # 512m maxmemory + overhead
worker:     { mem_limit: 1g,    cpus: "1.0" }
worker-heavy:{ mem_limit: 1500m, cpus: "1.0" }
```
Postgres ko OOM-killer se bachane ke liye uska limit reserved + generous rakho. **Effort:** 1–2 ghante (+ ek load test).

### P1-2 · SQLAlchemy pools PgBouncer/Postgres budget se 3-4x bade
**Evidence:** async `pool_size=20, max_overflow=30` (=50/process) `app/models/base.py:85`; sync `pool_size=10, max_overflow=20` (=30) `base.py:49`; PgBouncer `POOL_MODE=session, DEFAULT_POOL_SIZE=25` `compose:132-135`; Postgres `max_connections=100` `compose:99`.

**Problem:** **Session** pooling mode me PgBouncer multiplexing nahi deta — har held client-conn = ek server-conn. 2 web workers × async-pool 20 persistent = **40 held conns > 25 server pool** → PgBouncer pe queueing; aur worker/scheduler/migration pools milake Postgres ke 100 cap ke kareeb. Contention pe `pool_timeout` (default 30s) tak request hang, phir 500.

**Fix:** Pools ko budget ke andar size karo — session mode me chhota = sahi:
```python
kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800, pool_timeout=10)
```
2 workers × 10 = 20 ≤ PgBouncer 25 ≤ PG 100, baaki celery/migration ke liye headroom. (Ya PgBouncer ko `transaction` mode + asyncpg `statement_cache_size=0` — zyada multiplexing, par jyada change.) **Effort:** ~half din with a quick load test.

### P1-3 · Observability: RED metrics + LLM-health export missing; traces unwired
**Evidence:** `/metrics` LLM block **legacy `vertex_client`** se padhta (`app/api/health.py:340-343`) jabki asli data `app/platform/llm_metrics.py` me record hota (`free_ai.py:428-430`) — exported nahi. `RequestTracingMiddleware` duration **log** karta par histogram export nahi (`middleware/__init__.py:117-122`). OTel/Tempo: Tempo container chalta hai par app me koi OTel instrumentation nahi (grep: sirf `ENABLE_OTEL` flag-string).

**Problem:** Sabse valuable scale-signals Prometheus me nahi: **per-endpoint request-rate / error-rate / p95-p99 latency** (RED), **free_ai provider ok-rate/latency**, **Celery queue-depth**, **DB pool saturation**. Exported LLM metrics galat source se (stale). Tempo idle resource khaa raha. Scale pe partially blind.

**Fix:**
- `/metrics` LLM block ko `app.platform.llm_metrics` pe point karo (sahi source).
- RED histogram add karo — `prometheus-fastapi-instrumentator` (1 line) ya middleware me `Histogram`.
- Celery queue-depth gauge (`redis llen` per queue) + DB pool gauge (`engine.pool.checkedout()`) export karo.
- Tempo ya to OTel-instrument karo (`opentelemetry-instrumentation-fastapi`) ya stack se hatao. Sentry traces (10%) ab APM cover karta — Tempo optional.

**Effort:** 0.5–1 din. **Impact:** Scale pe actual visibility (p95, error-rate, provider-health, queue-backlog).

---

## P2 — Backlog (correctness/cost hygiene)

- **Schema-management drift** — boot pe `Base.metadata.create_all` (`base.py:249`) + hardcoded `ALTER` dict (`base.py:226-238`) + Alembic (`main.py:134-136`) teeno saath. `create_all` column-changes handle nahi karta; teen mechanism aapas me lad sakte. **Fix:** Alembic ko single source banao; prod me `create_all` dev/test-only gate karo. *(careful, medium effort)*
- **Call-admission semaphore per-process** — `asyncio.Semaphore(max_concurrent_calls=10)` (`telephony/call_manager.py:106-107`) worker-local hai (comment line 100). WEB_CONCURRENCY=2 → effective cap **20, na ki 10**. Single box + FREE real-time STT/TTS pe yeh CPU saturate kar sakta (P1-1 ke no-cpu-limit ke saath compounding). Voice DLT-gated hai isliye P2, par voice launch se pehle distributed admission counter (Redis) + capacity test zaroori.
- **FAIL-OPEN billing meter** — infra-fail pe usage meter nahi hota (revenue leak) jabki call chalti rehti. Reliability ke liye sahi default, par ek **daily reconciliation job** add karo (call-logs vs metered-usage diff → alert) taaki silent leak na ho.
- **Circuit-breaker state per-process** — `free_ai.py:112-115` module-global; har uvicorn/celery process apna dead-provider alag se seekhता → N× wasted probing. **Fix (optional):** cooldown state Redis me share karo.
- **`/metrics` public + `psutil.cpu_percent(interval=0.1)`** har scrape pe 100ms block + unauthenticated (`health.py:454`). **Fix:** interval=0 (non-blocking) + internal-network restrict.
- **`__main__` me `reload=True`** (`main.py:1277`) — agar koi prod me `python app/main.py` chala de to footgun. Guard ya hata do.

---

## What's already done right (credit где due)

- **Async hygiene excellent** — httpx 47 files, sync `requests.<verb>(` sirf 1, ML load `run_in_executor` me (`main.py:183`), routes async-DB only (`Depends(get_db)` sync = **0**). Event-loop blocking ka classic killer yahan nahi hai.
- **Celery prod-grade** — `acks_late`, `reject_on_worker_lost`, `prefetch_multiplier=1`, `max_tasks_per_child`, time-limits, heavy/light queue split (`worker.py:91-122`).
- **Degradation discipline** — rate-limit/redis/DB sab fail-open, in-memory fallbacks, DLQ recorder, escalating circuit-breaker (`free_ai.py:122-142`).
- **Health probes correct** — `/health/live` (no deps), `/health/ready` (DB+Redis, 503), Docker healthcheck liveness pe (dependency-blip pe restart nahi) — yeh sahi design hai.
- **Prod-down lessons baked** — fastembed/silero models image me baked (`Dockerfile.lock:54-61`), KB prewarm off-loop, boot-grace guards.

---

## Remediation roadmap

**Week 1 (P0 — ~1 din total, scale ka prerequisite):**
1. uvicorn `--proxy-headers --forwarded-allow-ips="*"` (P0-2) — 1 line.
2. Broker Redis `noeviction` + `Cache.set` fail-soft (P0-1 quick) — 30 min.
3. (stretch) alag cache-Redis container (P0-1 proper).

**Week 2 (P1) — ✅ IMPLEMENTED (deploy-pending), see "P1 implementation notes":**
4. ✅ Container mem/cpu limits, VPS RAM ke hisaab se (P1-1).
5. ✅ DB pool re-size + recycle/timeout (P1-2).
6. ✅ llm_metrics + queue-depth export; RED via Loki LogQL (P1-3, multi-worker rationale notes me).

**Backlog (P2) — partial done (see "P2 implementation notes"):** ✅ billing meter-observability · ✅ `/metrics` hardening (non-blocking CPU) · ✅ dev-only reload guard · ✅ schema gate added (`DB_CREATE_ALL`; Alembic cutover deferred) · ⏸ distributed call-admission (voice scale-up se pehle) · ⏸ shared circuit-breaker (latency-risk, defer).

**Reality check:** Single VPS ka SPOF known + spend-blocked hai (CLAUDE.md) — woh yahan deliberately P0/P1 me nahi rakha. Par P0-1 aur P0-2 fix kiye bina 2nd server lena bekaar hai: load multiply hoga to woh bottleneck hardware me nahi, in 2 jagah hai.

---

## P1 implementation notes (2026-06-15)

**VPS facts** (`/health/deep` se live): **16 GB RAM, 4 cores**, ~2.8 GB used (17.6%), 50 GB disk free. Khoob headroom — limits protective hain, throttling nahi.

**P1-1 container limits** (`docker-compose.vps.yml`, non-swarm `mem_limit`/`mem_reservation`/`cpus` — `docker compose up` honor karta):

| Service | mem_limit | cpus | reason |
|---|---|---|---|
| app | 3g | 2.0 | embedder+torch ×2 uvicorn workers |
| db | 2g | 2.0 | generous — Postgres OOM-kill se bachao |
| worker | 2g | 1.5 | ML/scraping jobs |
| worker-heavy | 2.5g | 1.5 | heavy LLM/ML/bulk |
| redis | 512m | 1.0 | maxmemory 256m + AOF overhead |
| redis-cache | 384m | 0.5 | maxmemory 256m + overhead |
| pgbouncer | 256m | 0.5 | tiny |
| scheduler | 512m | 0.5 | beat only |

Sum of caps ≈ 11.2g < 16g (obs-stack + host ke liye ~4.8g bachta). Deploy ke baad `docker stats` se tune karo.

**P1-2 DB pool** (`app/models/base.py`): async `pool_size 20+30 → 5+5`, sync `10+20 → 3+2`, + `pool_recycle=1800`, `pool_timeout=10`. Ab ~4 engine-processes × 5 = 20 baseline ≤ PgBouncer 25 ≤ PG 100. Pehle 2 web × 50 = 100+ potential = PgBouncer/PG exhaust risk.

**P1-3 observability** — `/metrics` me ab: `leadgen_llm_provider_ok_rate{provider}`, `_calls`, `_avg_latency_ms`, `leadgen_llm_fallback_rate` (REAL source `llm_metrics`, pehle legacy `vertex_client` empty tha) + `leadgen_celery_queue_depth{queue}`. Dono **shared-store** (file/redis) = multi-worker correct.

> **RED metrics ka decision:** `WEB_CONCURRENCY=2` (2 uvicorn processes, 1 `/metrics` port) ke saath **in-process counters reliable nahi** — har scrape random worker pe, `rate()` toot-ta hai. Isliye in-process HTTP counters ship NAHI kiye. Request rate/error/latency ka data `RequestTracingMiddleware` already structured logs me likhta (`status_code`, `duration_ms`) → **Loki me hai**. Grafana LogQL se RED:
> ```logql
> # error-rate:   sum(rate({app="leadgen"} | json | status_code>=500 [5m]))
> # p95 latency:  quantile_over_time(0.95, {app="leadgen"} | json | unwrap duration_ms [5m])
> ```
> Agar dedicated Prometheus RED chahiye → `prometheus-client` multiprocess mode (env `PROMETHEUS_MULTIPROC_DIR` + shared tmpfs) — naya dep + lock-refresh, alag task.

**Suggested alert** (`monitoring/alert_rules.yml` me add karo): `leadgen_llm_fallback_rate > 0.4 for 10m` (voice/content degraded) · `leadgen_celery_queue_depth > 500 for 10m` (worker stuck/starved).

**⚠️ Verify separately:** `/health/deep` ne `workers: 0` (degraded) dikhaya — ya to `inspect().active()` ka broadcast-timeout artifact hai (web container se), ya Celery worker genuinely down. Live check: `docker ps | grep -E "worker|scheduler"` + `docker exec leadgen_worker celery -A app.worker inspect active`. Agar sach me 0, durable scheduler process nahi ho raha (CLAUDE.md ke against) — alag se dekho.

---

## P2 implementation notes (2026-06-15)

**Implemented (safe subset):**
- **Billing meter observability** (`app/billing/lead_usage.py`) — fail-open meter ab SILENT nahi: `record_qualified_lead`/`add_topup_leads` ka write fail ho to ERROR log (Loki/alertable) + durable record main redis list `billing:meter_failures` (noeviction → kabhi evict nahi). Replay/inspect: `redis-cli lrange billing:meter_failures 0 -1`. Call kabhi block nahi hoti (fail-open intact), par revenue-leak ab visible + recoverable.
- **`/metrics` CPU non-blocking** (`app/api/health.py`) — `psutil.cpu_percent(interval=0.1→None)` (har scrape pe 100ms event-loop block hata).
- **Dev-only reload** (`app/main.py`) — `reload=settings.is_development` (prod me accidental `python app/main.py` reload-storm na de).
- **Schema gate** (`app/models/base.py`) — `DB_CREATE_ALL` env (default `1` = aaj jaisa). Alembic-only cutover ke liye opt-in `0` (blind flip nahi — neeche).

**Why meter-observability instead of a reconciliation job:** ek sahi reconciliation ko billable-event ka INDEPENDENT source-of-truth chahiye + exact per-client/period attribution. DB me `LeadStatus.QUALIFIED` hai par voice-qualification se uska 1:1 mapping live-DB verify kiye bina pakka nahi — guess-based job = false alarms. Isliye immediate safe win = meter-failure ko observable+recoverable banana. Full reconciliation (meter vs DB lead-status, per-client) = future enhancement, live-DB attribution verify karke.

**DEFERRED (with rationale — blind nahi karna):**
- **Schema Alembic cutover** — code-gate add kiya (`DB_CREATE_ALL=0`), par flip NAHI kiya. `create_all` band karne se pehle Alembic migrations ko live DB ke against verify karna zaroori (`alembic upgrade head` clean, koi missing table/column nahi) — warna boot pe schema-gap. Cutover live-DB access ke saath, low-traffic window me.
- **Shared circuit-breaker** (`free_ai` cooldown → Redis) — voice critical-path latency-sensitive hai; har LLM attempt pe Redis read add karna latency + coupling risk. Per-process breaker already fast converge karta (har process seconds me seekh leta). Tab karo jab multi-process dead-provider probing measurably waste dikhe — local-cache + async best-effort Redis sync pattern se.
- **Distributed call-admission** (per-process `Semaphore(10)` → Redis counter) — abhi effective cap = N×10 (per uvicorn worker). Voice DLT-gated hai = launch path nahi; voice scale-up se PEHLE Redis-based global admission + capacity test karo (single box + FREE real-time STT/TTS pe CPU saturation se bachne ke liye).

---

## Verification appendix (live confirm karne ke commands)

```bash
# P0-2: proxy-IP bug — 2 alag XFF se hit, dono counters alag hone chahiye (abhi same honge)
for ip in 1.1.1.1 2.2.2.2; do curl -s -H "X-Forwarded-For: $ip" https://leadsgenai.in/api/... ; done
# container ke andar uvicorn args confirm:
docker exec leadgen_app ps aux | grep uvicorn   # --proxy-headers present?

# P0-1: Redis eviction policy + role-mixing
docker exec leadgen_redis redis-cli config get maxmemory-policy   # expect: allkeys-lru (problem)
docker exec leadgen_redis redis-cli info keyspace                  # broker+cache+state ek hi db0 me?
docker exec leadgen_redis redis-cli info stats | grep evicted_keys # >0 = already losing data

# P1-1: container limits
docker stats --no-stream   # MEM LIMIT column "/ <host RAM>" dikhe = no per-container cap

# P1-2: connection pressure
docker exec leadgen_db psql -U leadgen -c "select count(*),state from pg_stat_activity group by state;"
```

*Yeh audit code-read pe based hai; upar ke commands se live-state confirm karke P0 se shuru karo.*

---

## Deploy handoff (P0-1 + P0-2)

**Kya badla:** `Dockerfile.lock` (uvicorn `--proxy-headers --forwarded-allow-ips='*'`) · `app/middleware/__init__.py` (`_real_client_ip` XFF) · `docker-compose.vps.yml` (naya `redis-cache` container + main redis `noeviction` + `CACHE_REDIS_URL` env) · `app/cache/__init__.py` (`get_cache_redis_client` + `Cache` fail-soft) · `.env.example`.

**Yeh image + topology change hai** (sirf code nahi) — `--no-deps app` se kaam NAHI chalega; naya container banana hai aur redis recreate hoga.

```bash
# 1) Local (Windows) — pipeline:
python scripts/prod_check.py
scripts\run_tests.bat          # pytest_run.log Read karo (~80+ green)
# git push (bat ke andar Windows git)

# 2) VPS (Git ka ssh):
cd /opt/leadgen && git pull
docker compose -f docker-compose.vps.yml build app            # naya Dockerfile CMD + cache code
docker compose -f docker-compose.vps.yml up -d                # redis-cache create + app/redis recreate
#   ^ NOTE: redis recreate = ~1-2s broker blip (AOF persist, Celery auto-reconnect). Acceptable.

# 3) Verify:
sleep 16
curl -fsS https://leadsgenai.in/health        # environment: production
docker exec leadgen_redis redis-cli config get maxmemory-policy        # noeviction
docker exec leadgen_redis_cache redis-cli config get maxmemory-policy  # allkeys-lru
docker exec leadgen_app ps aux | grep -- --proxy-headers               # flag present
# proxy-IP fix: do alag XFF se 100+ req → alag-alag 429 (pehle saath trip hote)
```

**Rollback (sabse risky single change = redis noeviction):**
- Quick: `docker-compose.vps.yml` me main redis ko wapas `allkeys-lru` + `CACHE_REDIS_URL` lines hata do → `docker compose -f docker-compose.vps.yml up -d` (code backwards-compatible, `CACHE_REDIS_URL` unset = purana behaviour).
- Full: `git revert <commit>` → rebuild + `up -d`.
- proxy-headers rollback: Dockerfile CMD se flags hata ke `build app` + recreate.

**Deploy ke baad watch karo:** `docker exec leadgen_redis redis-cli info stats | grep -E "evicted_keys|keyspace"` — agar main redis pe `evicted_keys>0` ya OOM dikhe to `--maxmemory` 256mb→384mb badhao (RAM allow kare to).
