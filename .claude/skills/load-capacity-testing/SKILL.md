---
name: load-capacity-testing
description: Load testing + capacity headroom on single-VPS free stack — API rps limits, WEB_CONCURRENCY, PgBouncer pool, Celery worker saturation, voice concurrent-call ceiling, Redis memory, when-to-scale triggers. Use jab "kitne customers/calls handle honge", launch/campaign spike se pehle, slow-response complaints pe, ya 2nd-server decision se pehle.
---

# Load & Capacity Testing (ceiling JANO, guess mat karo)

> Enterprise audit skill. Single VPS (Mumbai, ~11 containers) = shared everything. **Enterprise bar = numbers: X rps sustained, Y concurrent calls, Z% headroom.** Pehle `context-first`.

## Repo truth (capacity-relevant knobs)
- **Web**: uvicorn `WEB_CONCURRENCY=2` HTTP-only (heavy jobs KABHI web process me — 3 prod-downs ka sabak). Public endpoint me KB/ML = thread + hard timeout.
- **Workers**: `leadgen_worker` concurrency=4; beat = alag `leadgen_scheduler` container (2026-07-05). Queue depth rule: **worker recreate ke baad `redis-cli llen celery`; >500 = `del celery`** (transient, beat re-schedules).
- **DB**: Postgres via PgBouncer :6432 (pool = real ceiling, direct conn count nahi).
- **Rate limits**: `PlanTierRateLimitMiddleware` 60/200/500 rpm per tier (`PLAN_RATE_LIMIT=1`) — capacity SHIELD hai, load test isse bypass karke raw ceiling bhi napo.
- **Voice**: per concurrent call = WS + STT (Groq) + LLM + EdgeTTS streams — ceiling CPU/network se pehle PROVIDER rate-limits pe aayega (Groq rpm, Gemini pool 9 keys). Breaker cooldowns = degraded, down nahi.
- **Boot-grace**: heavy daily jobs boot-window me skip (restart-storm guard) — load test ke dauran restart mat karo warna results corrupt.

## Load test loop (free tools, prod-safe)
1. **Baseline first**: Grafana 7-day p95 latency, CPU, RAM, PgBouncer active/waiting, Redis mem — screenshot/note.
2. **Tool**: `hey` ya `wrk` apne machine/sandbox se (VPS pe mat chalao — khud ko test karega). Targets: `/` (static-ish), `/audit` (lead magnet, DB write), `/api/data/niches` (read), `/b/{slug}` (tenant path).
3. **Ramp**: 5 → 20 → 50 → 100 concurrent, 60s each. Record: p50/p95/p99, error %, aur SAATH me VPS side `docker stats` + PgBouncer `SHOW POOLS`.
4. **Find the knee**: jahan p95 2× ho jaye ya errors >1% = practical ceiling. Us number ka **60% = safe operating limit** (headroom policy).
5. **Voice concurrency**: `/app/test-call` web-call se N parallel sessions (FREE path) — 2, 4, 8... jahan TTS lag/STT queue dikhe = ceiling. Phone minutes MAT jalao iske liye.
6. Off-peak (IST raat) chalao, `ops_alerts` ko heads-up suppress window do, aur Uptime Kuma alert pause — warna self-inflicted incident pings.

## Scale triggers (2nd-server/upgrade decision data-driven)
- Sustained CPU >70% peak-hours ya RAM >85% → vertical upgrade pehle (sasta).
- PgBouncer waiting >0 regularly → pool tune, phir DB resources.
- Celery queue latency (enqueue→start) >5min regularly → worker concurrency ya dedicated worker container.
- Voice concurrent demand > provider-key ceiling → Gemini pool me keys add (admin page, no-restart) pehle, infra baad me.
- In sab ke numbers `docs/SESSION_LOG.md` me — HA/2nd-server EXTERNAL-BLOCKED hai (spend), par jab unlock ho to yeh data = business case.

## Output
Ceiling table (surface × knee-point × safe-limit × current-peak × headroom %) · bottleneck ranked list · knob changes shipped · scale-trigger thresholds wired into alerts.

## Related repo skills
`slo-error-budget` (targets) · `observability-ops` (metrics) · `leadgen-infra-doctor` (bottleneck root-cause) · `llm-quota-ops` (provider ceilings) · `scheduler-job` (worker capacity).
