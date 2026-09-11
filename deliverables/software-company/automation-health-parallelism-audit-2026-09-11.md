# Automation Health + Parallelism Audit

**Repo:** `main` @ `33189b70` · **Date:** 2026-09-11 · **Status:** RESEARCH (read-only, no files modified)
**Answers the owner's ask:** "Automation check karo" + "Ye automation system parallel me sab kuch chalaye"

---

## 1. Executive verdict

| Question | Answer | Evidence label |
|---|---|---|
| Do all 54 scheduler jobs have a *liveness* signal? | **Yes — 54/54** | CODE-PRESENT |
| Do they have a *productivity* signal (did the job actually DO anything)? | **No — 1/54** | CODE-PRESENT |
| Are any jobs reporting green while doing nothing? | **Yes — 2 confirmed fake-green** | CODE-PRESENT |
| Is all automation running in parallel? | **No — 4 concrete serialisation blockers** | CODE-PRESENT |
| Is the Redis backlog guard automatic? | **No — display/advisory only** | CODE-PRESENT |

**Bottom line:** the platform can tell you a job *ran*. It cannot tell you a job *worked*. That is the
core defect behind "automation check karo", and it is why the owner's Telegram/dashboard cannot be
trusted as-is.

---

## 2. Health surface — what exists

`app/platform/automation_health.py` measures **liveness only**.

- `record_run()` writes `{job, ok, s, duration_ms, note, at, error_class, error_message, trigger, started_at}`
  to `data/job_runs.jsonl` + a latest-per-job snapshot `data/job_heartbeats.json`
  (both via `runtime_data_authority`).
- `health()` (`:725`) compares `EXPECTED_GAP_MIN` against that snapshot →
  `ok` / `last_failed` / `overdue` / `never_ran`.
- `EXPECTED_GAP_MIN` has **74 entries**; **all 54 `JOB_META` jobs are covered (0 missing)**.
  The extra 20 are legacy/continuous jobs (crm-sync, brain-*, vertex-*, content_os.*, self_improve).
- Liveness is written in `team_scheduler._run_job_direct` **finally block** (`:459-481`) → 54/54.

### 2.1 Signal quality per job

| Job group | EXPECTED_GAP entry | Last-run record | Wired | Signal |
|---|---|---|---|---|
| `content` | ✅ | ✅ | ✅ | **PROVEN** (output probe + engine-skip ledger) |
| `heartbeat`, `content_approval_notify` | ✅ | ✅ | ✅ (beat) | **NONE — no body branch** |
| `daily_video` | ✅ | ✅ | ✅ | PARTIAL (enqueue-only, no render-completion probe) |
| other 50 jobs | ✅ | ✅ (code path) | ✅ | PARTIAL (liveness only; bodies flag-gated no-op when OFF) |

### 2.2 The two fake-green jobs (must not be shown green)

`heartbeat` and `content_approval_notify` have **no body branch inside `_run_job_inner`**
(`team_scheduler.py:572-1673`). They record a green run while executing nothing.

### 2.3 Other gaps

- **No `next_expected_run` field exists anywhere** — it is computed on read from cadence strings.
- `retry_count` lives only in `automation_logs` (`automation_log_service.py:19`), **not** in the heartbeat.
- `overdue` is computed, never stored.
- Local `data/job_heartbeats.json` holds only **12** jobs → LOCAL-ONLY, not production proof.
- Existing routes: `GET /api/growth/infra/automation-health` (`growth.py:894`), `/control-center/rca`
  (`control_center.py:428`), `/system-health-detail` (`system_health.py:217`), admin `/ops-snapshot`
  (`admin_dashboard.py:1361`). **No dedicated per-job automation-health route exists.**
- Dead-man mechanisms that ARE wired: `automation_health.run_watch()` (`:931`, via `watchdog` job),
  `self_improve_revive` beat (`worker.py:819`), `heartbeat` 5-min job (`worker.py:825`),
  `boot_grace.py`, `loop_supervisor`. None are dead code.

---

## 3. Parallelism — four concrete serialisation blockers

1. **`team_scheduler.py:1683-1966` `scheduler_loop`** awaits `_run_job(...)` **sequentially**.
   One slow job blocks the entire tick (in-process path).
2. **`worker.py:54-63` HEAVY_STAFF_JOBS** (`qa`, `trainer`, `blog`, `content`, `hot_queue_brief`,
   `hot_queue_owner_pack`, `digest`, `prospect`) route to the `heavy` queue;
   `docker-compose.vps.yml:390` worker-heavy runs `--concurrency=1` → **8 jobs strictly serialised**.
3. **`app/utils/file_lock.py`** cross-process lock is taken in `record_run` (`automation_health.py:416`)
   and on every JSONL rewrite → **serialises workers on the heartbeat snapshot**.
4. **`content` engine loop** — `team_scheduler.py:572-1673` is one giant if/elif; `content` runs ~12
   engines sequentially under a single budget (`_run_content_engine` `:514`,
   `CONTENT_TIME_BUDGET_S` default **420** `:856`) → an overrun **silently skips queued engines**.

Additional:
- `docker-compose.vps.yml:443` worker-video `--concurrency=1`; default worker `:336` `--concurrency=4`
  on queues celery,calling,scraping,reporting,sync,training.
- `app/marketing/daily_video.py:509` `for c in clients:` sequential enqueue; caps
  `max_per_run()` default 10 (`:510`), `max_pending()` default 2 (`:522`).
- Rate limits `worker.py:224-228` (calling 20/m, scraping 5/m, brain_training 10/m).
- `asyncio.to_thread` at `team_scheduler.py:706,1482,1555,1634` is awaited inline — still sequential.

### 3.1 Redis queue-depth guard — NOT automatic

- `system_health.py:175-192` — **display only** (>200 warn, >500 bad).
- `control_center.py:454-462` — **advisory text** only.
- `admin_dashboard.py:1405-1490` `/ops/celery-trim` — the **only real trim**, and it is **manual**
  (requires `confirm=true` and depth ≥ `min_depth` → `r.delete("celery")` at `:1456`).
- Alert: `automation_health.py:528` `QUEUE_BACKLOG_ALERT=50` → `queue_backlogged` email
  (gated by `AUTOMATION_HEALTH_ALERTS`). DLQ trim at `worker.py:386`.

### 3.2 Circuit breaker — per-provider, does not globally block

`free_ai.py:257-266` — escalating **60s → 1800s per-provider** cooldown, skipped per call (`:953`).
A call stalls only when **all** providers are cooling down. `VOICE_CIRCUIT_FAIL_THRESHOLD` default 5.

---

## 4. Feature inventory — inert / blocked

From `docs/FEATURE_INVENTORY.md` (346 LIVE · 21 WORKING_BUT_INERT · 3 PARTIAL · 3 EXTERNALLY_BLOCKED · 3 REMOVED).

### 21 WORKING_BUT_INERT
| # | Feature | Gate |
|---|---|---|
| 8 | Content calendar | — |
| 13 | LinkedIn publishing | — |
| 18 | Auto-approve policies (own-brand canary) | — |
| 33 | Content-hash binding | `HARNESS_SESSION_EVENTS` |
| 35 | Version identity | — |
| 58 | Hot Queue (owner action) | — |
| 59 | `/app/inbox` | — |
| 64 | Sales automation | `SALES_AUTOPILOT_WHATSAPP_ENABLED` |
| 135 | Advanced/Combo ₹5,999 | `COMBO_PRODUCT` router unmounted |
| 140 | Trial | — |
| 159 | Onboarding pipeline | `ONBOARDING_PIPELINE` |
| 202 | Governed release helper | agents unarmed |
| 234 | Audit/replay | `HARNESS_SESSION_EVENTS` |
| 236 | Tool execution | — |
| 238 | Enforcement mode | — |
| 241 | Canary allowlists | `DSH_AGENT_ALLOWLIST` |
| 274 | A2A surfaces | — |
| 285 | Web push | VAPID |
| 312 | Tracing | `ENABLE_OTEL` |
| 318 | Langfuse | — |
| 345 | Inbox | — |

### 3 PARTIAL
`4` Reels/video copy · `15` Pinterest · `352` Duplicate/legacy UI

### 3 EXTERNALLY_BLOCKED
`44` ToS-blocked scrapers · `89` Cold WhatsApp restrictions (**ban risk**) · `93` Twilio fallback

---

## 5. Doc ↔ code contradictions (must be reconciled, code wins)

1. `system_health.py:175` comment calls ">500 backlog = `del celery`" a **rule**, but no code
   auto-deletes — only manual/advisory paths exist.
2. `automation_health.py:122-129` registers **20 legacy jobs** (crm-sync, brain-*, vertex-*) that
   `worker.py:884` **strips from beat when `ENABLE_LEGACY_BEAT=0`**. They can never run in production
   yet sit in the dead-man registry and report `never_ran` — permanent false alarms.
3. `automation_health.py:1-11` claims the heartbeat covers "har job"; `heartbeat` and
   `content_approval_notify` have **no body branch**, so their green run is a no-op.
4. Minor cadence drift `JOB_META` vs beat: `engineer_finops` 09:00 vs 09:05;
   `readiness_digest` 08:30 vs 08:35; `whatsapp_automation` "hourly" vs beat **9am–7pm only**.

---

## 6. What the design must therefore deliver

1. An **output-level (productivity) signal** per job family — the 53/54 blind spot is the core defect.
   `EXPECTED_GAP_MIN` stays the single source for expected cadence; no second registry.
2. Fake-green jobs (`heartbeat`, `content_approval_notify`) either get a real body or are explicitly
   marked **NO-OP** in the health surface — **never green**.
3. A dedicated per-job automation-health route (the existing four routes are partial/diagnostic).
4. A decision on each of the four serialisation blockers: change it, or deliberately leave it with a
   stated reason.
5. Reconciliation of the 4 doc↔code contradictions above.

---

## 7. Evidence labels used

PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN.
Everything in this document is **CODE-PRESENT** unless stated otherwise.
`data/job_heartbeats.json` observations are **LOCAL-ONLY** and are not production proof.
