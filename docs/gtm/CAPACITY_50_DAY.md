# Product-1 backend capacity — 50 paid/day (honest ceiling)

**Not a claim that 50/day is live.** North-star remains ledger `paid_today`.
This sheet is the backend factory: visits + `/start` + `onboard_client`.

Probed: `scripts/capacity_baseline.py` at **2026-08-15 01:16Z** + loadtest
`scripts/capacity_loadtest.py` (5 concurrent × 10s, remote). JSON copies live
under `docs/evidence/` (gitignored `*.json`; this markdown is the tracked sheet).

## Live baseline (DIRECT_HOST_VERIFIED, prod `91958c23`)

Re-probe **2026-08-15 02:41Z**: host 7551 / 15992 MB · load 0.99 1.12 1.00 · DB via **pgbouncer:6432**.
`WEB_CONCURRENCY=2`. `CELERY_ONBOARD_QUEUE` UNSET. `paid_today=0` (not 50/day).

**Heavy jobs (read-only, todo 11):** `app.tasks.staff_jobs.self_improve_tick` (`channel_experiments` / `approval_pending`), `app.tasks.staff_jobs.run_staff_job`, `[kb-warmup]` FastEmbed ~96s (`solar_residential` / chroma fallback). Queue `heavy` llen=0 at 02:41Z; worker CPU **0.46%** after warmup (same-day 01:16Z was **155%** / llen=2). Recurring warmup is why onboard→heavy stays **NO-GO**. `dlq:dead=24` — do not flush.

Earlier same-day 01:16Z sheet kept below for the 155% snapshot.

Host (01:16Z): 7873 / 15992 MB used · load 2.73 3.18 2.03 · DB via **pgbouncer:6432**
(not `db:5432`). Redis broker 5.01M / 256M. `WEB_CONCURRENCY=2`.

| Container | CPU | RAM |
|---|---|---|
| leadgen_app | 1.48% | 1.70 / 3 GiB (57%) |
| leadgen_worker | 0.36% | 693 MiB / 2 GiB |
| leadgen_worker_heavy | **155%** | 1.41 / 2.44 GiB (58%) — already busy; do not dump 50 onboardings here without measuring |
| leadgen_worker_video | 0.17% | 108 MiB / 1.95 GiB |
| leadgen_dsh_worker | 0.24% | 75 MiB / 768 MiB |
| leadgen_scheduler | 0.00% | 102 MiB / 512 MiB |
| leadgen_db | 0.00% | 127 MiB / 2 GiB |
| leadgen_pgbouncer | 0.01% | 1.1 MiB / 256 MiB |
| leadgen_redis | 2.41% | 6.6 MiB / 512 MiB |

Queues at probe: celery=0 · heavy=**2** · video=0 · dsh=0 · dlq:failed_tasks=0 · dlq:dead=23.
PgBouncer `SHOW POOLS` / `pg_stat_activity` count was skipped (no interactive psql in this probe). Pooler RSS is idle; **do not** point app back at `@db:5432`.

## Current knobs (CODE-PRESENT, docker-compose.vps.yml)

| Surface | Knob | Cap |
|---|---|---|
| Web | `WEB_CONCURRENCY=2` hardcoded, mem 3g, 2.0 cpu | HTTP-only; do not raise until loadtest knee is the web workers |
| Worker | `-Q celery,calling,scraping,reporting,sync,training` conc=4, mem 2g | default `onboard_client` lands here |
| Heavy | `-Q heavy` conc=1, mem 2500m | ML/LLM isolation; already 155% CPU at idle-ish GTM |
| Video | `-Q video` conc=1, mem 2g | creative only |
| DSH | conc=1, separate image | not app-skew |
| DB | Postgres via PgBouncer :6432 | waiting>0 → pool tune before vertical |
| Redis | broker + cache | recreate flood: `llen celery` >500 → del celery |

## 50/day reverse funnel (planning)

5k–25k visits → hundreds magnets → ~125–200 `/start` → **50 paid** → **50 `onboard_client`**.
Spread over 24h ≈ 2 onboardings/hour — celery conc=4 is enough **if** jobs do not burst.

## Burst isolation (INERT)

`CELERY_ONBOARD_QUEUE` live = **UNSET** (OFF). When ON, `onboard_client` routes to existing
**heavy** worker (already consumed). No new queue name — unconsumed queues orphan tasks.
**Do not arm now:** heavy is already 155% CPU with 2 queued jobs. Arm only after measured
enqueue→start >5 min under a 50-job **staging** burst.

50 simulated onboardings = `tests/test_onboard_client_burst.py` (fake `sim-onboard-*` ids,
never Jiya, never-raise). Not a live Celery enqueue against real tenants.

## Load test (2026-08-15 06:28 IST, 5 concurrent × 10s, remote)

| URL | n | p50 | p95 | errors | notes |
|---|---|---|---|---|---|
| `/health` | 129 | 0.33s | 0.82s | 0 | all 200 |
| `/` | 143 | 0.34s | 0.42s | 0 (5xx) | **43× 429** — anonymous rate-limit is the public knee, not CPU |

Knee = 5 concurrent on `/` (429, not 5xx). **Safe limit ≈ 60% of knee ≈ 3 concurrent
anonymous.** Higher 20/50/100 ramps skipped — they would only multiply 429s and trip
Uptime. Do not raise `WEB_CONCURRENCY` based on this — the 429 shield fired first.

## LLM quota (free stack)

50 × (website scrape + KB seed + first pack) vs Groq TPD / Mistral / Cerebras 429.
Fail-closed skip (`onboard_client` never-raises; sweep uses `ONBOARD_TIME_BUDGET_S=300`).
Paid LLM add forbidden. Watch circuit-breaker cooldowns.

## Go / no-go (owner)

| Surface | Knee | Safe limit | Current peak | Headroom |
|---|---|---|---|---|
| Anonymous `/` | 5 conc (429) | ~3 conc | this probe 1.5% app CPU | rate-limit bound, not RAM |
| `/health` | >5 conc in 10s | keep monitors light | p95 0.82s | OK |
| `onboard_client` burst | unmeasured live | 2/hour spread | heavy already 155% | **NO-GO for 50-at-once** |
| Paid/day live | n/a | ledger only | `paid_today=0` | do not claim 50/day |

- Kill ads if CAC > 1-month gross margin or onboard fail-rate red.
- Never write "50/day live" without `paid_today` billing-ledger evidence.
- Voice concurrent-call ceiling is out of scope (Swara/voice FROZEN).
