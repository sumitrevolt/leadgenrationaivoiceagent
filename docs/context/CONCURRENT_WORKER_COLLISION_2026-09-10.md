# 🚨 CONCURRENT WORKER COLLISION — 2026-09-10 15:11–15:20 IST

**Logged by:** team-lead (WorkBuddy / software-leadgen-24x7 team)
**Purpose:** stop any worker from clobbering in-flight work. **Read this before editing anything under
`app/dev_control/`, `app/models/dev_task*.py`, `app/admin/`, or `alembic/versions/026*`.**

---

## What happened

While this session's audit team (architect / PM / QA) was inventorying the repo, **another worker began
editing the same files and is still mid-flight**. Evidence (mtimes, all 2026-09-10 afternoon):

```
15:11:39  app/dev_control/lease_policy.py      (NEW)
15:11:39  app/dev_control/ledger_hash.py       (NEW)
15:12:05  app/models/dev_task_event.py         (NEW)
15:13:00  app/dev_control/reconcile.py         (MODIFIED)
```

Working tree at 15:20 IST (all **uncommitted**):

```
 M  app/dev_control/claims.py
 M  app/dev_control/reconcile.py
 M  app/dev_control/service.py
 M  app/main.py
 M  app/models/__init__.py
 M  app/models/dev_task.py
??  app/dev_control/lease_policy.py
??  app/dev_control/ledger_hash.py
??  app/models/dev_task_event.py
??  alembic/versions/026_add_dev_task_events.py
A   app/admin/__init__.py  main.py  models.py
A   app/admin/routes/{__init__,docker,system,tasks,workers}.py
A   app/admin/services/{__init__,docker_manager,system_monitor,task_ledger,worker_manager}.py
```

## 🔴 Two collisions — do NOT start this work, it is already underway

### Collision 1 — PHASE 2 (DevTask gap closure) is ALREADY DONE by the other worker

Our architecture record specified five gaps. **All five are already implemented in the working tree:**

| Gap we planned | Reality |
|---|---|
| add `parent_id` + `next_eligible_at` to `dev_tasks` | ✅ already added (`app/models/dev_task.py:15,35`) |
| NEW `DevTaskEvent` hash-chained audit model | ✅ `app/models/dev_task_event.py` exists, registered in `app/models/__init__.py`, has `prev_hash`/`event_hash`/`GENESIS_HASH`/`seq` |
| startup/beat-safe reconcile | ✅ `reconcile.py` has BOTH `reconcile_leases()` (async) and `reconcile_expired_leases_sync()` — docstring: *"blocking, opens its own session, NEVER raises. Safe for app startup and Celery beat"* |
| exponential backoff on requeue | ✅ `app/dev_control/lease_policy.py` — `BACKOFF_BASE_SECONDS=60`, `BACKOFF_CAP_SECONDS=900`, jitter applied AFTER cap, pure `plan_lease_reclaim()` |
| durable idempotency (kill process-local dict) | ✅ already killed — `service.py:125-128` says the guarantee *"now comes from the UNIQUE column `dev_tasks.idempotency_key`"* |
| alembic migration | ✅ `alembic/versions/026_add_dev_task_events.py` (untracked) |
| `claim_next` honours backoff | ✅ `claims.py` `_backoff_predicate`, explicitly backwards-compatible (NULL = eligible) |

**Verified by me:** all 6 files pass `python -m py_compile`.

### Collision 2 — a SECOND admin surface is being built (violates "one control plane")

`app/admin/` — a new FastAPI package mounted at `/admin/api/{system,workers,docker,tasks}`
(JSON API, **not** Jinja templates).

- It is **staged (`git add`) but NOT yet wired** — `app/main.py` still imports only `app.api.admin` /
  `app.api.admin_dashboard`; there is no `from app.admin...` import. So today it is **dead code**.
- `app/api/admin.py` **already exists** → this is a **duplicate admin surface**, which directly violates
  the owner's "ONE CONTROL PLANE — do not create unnecessary duplicate dashboards" rule.
- It also settles the open framework question: **this worker chose server-rendered/JSON FastAPI, not React.**

---

## ⛔ File ownership — DO NOT TOUCH

| Path | Owner | Status |
|---|---|---|
| `app/dev_control/{claims,reconcile,service}.py` | concurrent worker | **in-flight — DO NOT EDIT** |
| `app/models/dev_task.py`, `dev_task_event.py` | concurrent worker | **in-flight — DO NOT EDIT** |
| `app/dev_control/{lease_policy,ledger_hash}.py` | concurrent worker | NEW — DO NOT EDIT |
| `app/admin/**` | concurrent worker | staged, unwired — **DECISION NEEDED before anyone builds on it** |
| `alembic/versions/026_add_dev_task_events.py` | concurrent worker | NEW — do not create a competing 026 (two heads) |
| `app/main.py` | concurrent worker | modified — do not edit concurrently |

**Anyone creating a second migration numbered `026` will produce two Alembic heads and break the chain.**

## ✅ What this session changed instead (no overlap)

- `app/platform/automation_health.py` — `EXPECTED_GAP_MIN` **55 → 74 entries**. Added 19 jobs that were
  DECLARED in `app/worker.py` beat_schedule but absent from the dead-man registry, so they could **never**
  surface as overdue (a silent-failure class). Conservative gaps; verified `py_compile` OK + brace-matched
  dict (74 keys, all numeric).
  - Safe-by-construction note: a job with no recorded heartbeat gets status `never_ran` (`health()` `:749`),
    **not** `overdue`. So jobs that are dormant because `ENABLE_LEGACY_BEAT=0` strips them
    (`app/worker.py:884`) report honestly instead of firing false alarms.
- `AGENTS.md` — corrected stale prod SHA `5919c379` → `0b848b34`; `DSH_RUNTIME_ENABLED=0` → `=1`
  + allowlist `["jiya_makeover"]`; added **LINEAGE WARNING** (prod ≠ HEAD) and **TRUTH GATE** blocks.
- `docs/context/PHASE0_BASELINE.md`, `docs/context/FEATURE_PRESERVATION_MATRIX.md`,
  `docs/context/baseline_snapshots/`, `docs/architecture/24X7_ARCHITECTURE_RECORD.md` — new.

## 🔴 Owner decisions now forced

1. **Keep or delete `app/admin/`?** Keeping it means wiring it and retiring the duplicate `app/api/admin.py`
   surface; deleting it means the Owner Command Center must be built on the existing surfaces
   (`app/dev_control`, `frontend/`, `admin-dashboard/`). **Do not let both ship.**
2. **Who owns Phase 2 going forward?** The concurrent worker has it. Either hand it fully to them, or
   have them stop. Two writers on `app/dev_control/` will corrupt the ledger.
3. **Confirm React vs HTML?** The concurrent worker has effectively chosen server-rendered FastAPI/JSON.

## Rule for the next worker

Before editing anything: `git status --porcelain app/ alembic/` and check file mtimes against your session
start. If a file was touched **during** your session, it belongs to someone else — **coordinate, do not overwrite.**

---

## ➕ Ownership additions — 2026-09-10 15:45 IST (Nova, PHASE 3)

New files created this session. **Do not edit without coordinating.**

| Path | Owner | Status |
|---|---|---|
| `app/platform/worker_health.py` | Nova | NEW — stdlib-only pure liveness math |
| `app/models/dev_worker.py` | Nova | NEW — `dev_workers` ORM + async registry |
| `app/platform/omniroute_combo_health.py` | Nova | NEW — read-side adapter over the watchdog state file |
| `alembic/versions/027_add_dev_workers.py` | Nova | NEW — chains on **026**; do NOT renumber |
| `tests/test_dev_worker_registry.py` | Nova | NEW — 24 tests |
| `tests/test_omniroute_combo_health.py` | Nova | NEW — 20 tests |
| `app/models/__init__.py` | shared | Nova added 2 additive lines only (import + `__all__`) |

### ⚠️ Alembic chain hazard — READ BEFORE COMMITTING
`027_add_dev_workers.down_revision = "026_add_dev_task_events"`, but **026 is still git-untracked
(`??`)**. Committing/deploying 027 without 026 produces a broken chain. **Both must land together.**

### 🔍 Finding for the Phase 2 owner (not fixed — their file)
`DevTaskEvent` is imported at `app/models/__init__.py:45` but is **absent from `__all__`**, so
`from app.models import *` will not export it. Add `"DevTaskEvent"` next to `"DevTask"` at ~line 143.
