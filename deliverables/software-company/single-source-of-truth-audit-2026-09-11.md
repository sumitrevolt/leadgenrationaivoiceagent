# Single Source of Truth Audit — Admin Panel Readiness

**Repo:** `main` @ `33189b70` · **Date:** 2026-09-11 · **Status:** RESEARCH (read-only, no files modified)
**Answers the owner's ask:** "single source of truth admin panel ke saath GitHub repo jaise structured platform"

---

## 1. Verdict

**There is no single source of truth today. There are THREE task ledgers, and nothing in the code
syncs or reconciles them.**

| # | Ledger | Backend | Rows | Who reads it |
|---|---|---|---|---|
| 1 | `command_center/data/tasks.json` | file | **8** real tasks (`SUC-016` … `BRD-016`) | `app/api/bot_command_center.py:89` |
| 2 | `data/admin_tasks.db` → `tasks` table | SQLite inside checkout | **30** generic seed-like rows ("API task" / "To update") | `app/api/owner_command_center.py:191-206` |
| 3 | `dev_tasks` | Postgres (prod) / SQLite (dev) | **0** | `/api/dev-tasks/*` only — **absent from every owner surface** |

> **The most serious finding:** the owner's Command Center reads ledger #2 (30 generic rows), while
> the real work sits in ledger #1 (8 tasks). The only ledger with atomic claim / lease / heartbeat
> (ledger #3) is **empty and not shown to the owner at all**.

`grep` found **no module that reads or writes more than one** of these three. The only test,
`tests/test_council_ledger_sync.py`, proves idempotency of `council_ledger_sync.py` itself — it does
**not** guard against a second ledger. **Nothing in code enforces "one ledger". It is documentation only.**

---

## 2. State store inventory (top stores)

| Store | Backend | Writer(s) | Reader(s) | Canonical? | Divergence risk |
|---|---|---|---|---|---|
| `command_center/data/tasks.json` | file | `scripts/council_ledger_sync.py:905`, `build_tasks_json.py`, ~30 offline `command_center/scripts|patches/pilot_*.py`, `parse_tasks.py` | `app/api/bot_command_center.py:89`, `command_center/build.py:26` → `state.js`, `frontend/bot_command_center.html` | Doc says yes; manifest says `REBUILDABLE_CACHE` | **HIGH** — ~30 writers, **no runtime writer** |
| `dev_tasks` (DevTask plane) | Postgres prod / SQLite dev | `app/api/dev_tasks.py` (34 routes, 12 `missions/*`) | `/api/dev-tasks/*` only | Self-declared canonical (`app/models/dev_task.py:1`) | **HIGH** — 0 rows; on no owner surface |
| `data/admin_tasks.db` → `tasks` | SQLite in checkout | `app/admin/services/task_ledger.py` | `app/api/owner_command_center.py:191-206` | No | **HIGH** — 30 seed-like rows; not in the manifest |
| `data/workforce_live_status.json` | file (+ dual copy `var/runtime-data/`) | `scripts/autonomous_workforce_orchestrator.py:137`, `workforce_staleness_watchdog.py` | `owner_command_center.py:93`, `admin_dashboard.py:1493`, `app/utils/owner_feed.py` | STALE | MED — **now `NOT_INSTRUMENTED`**; guard `FORCE_UNVERIFIED_SOURCES` |
| `data/job_runs.jsonl`, `job_heartbeats.json`, `scheduler_last_ran.json` | file | Celery / beat | `app/platform/automation_health.py` → `control_center.py`, `system_health.py` | CODE-PRESENT | LOW |
| Redis `:6379/0` | Redis | `app/tasks/calling.py:374-397` (campaign status/lock), Celery broker, `app/platform/dlq_retry.py` | DLQ routes (`app/api/growth.py:1048`), `health.py:791` | CODE-PRESENT | LOW |
| `data/interactions.jsonl` | file | two writers | — | manifest `DUAL_WRITE_DRIFTED` | **HIGH** |
| `data/external_missions/` | file | `app/dev_control/external_agents/store.py` | missions API | CODE-PRESENT | MED — a **second** `dev_control` backend |
| `data/owner_feed_events.jsonl` | file | `app/utils/owner_feed.py` | owner feed | **UNKNOWN — not in the manifest** | MED |
| Postgres models | `app/models/*` (27 files, 28 alembic revisions) | SQLAlchemy | async API | only `sales.leads`, `governance.owner_os` | — |

**Store registry:** `app/platform/runtime_data_manifest.py` lists **51 store families**
(CUTOVER_COMPLETE 21 · LEGACY_IN_CHECKOUT 6 · REBUILDABLE_CACHE 20 · …).
`runtime_data_authority.py` is **not** a registry — it resolves one caller-supplied `store_id` at
operation time (LEGACY / MIGRATION_VALIDATION / CANONICAL). **No API exposes the registry.**

---

## 3. Concrete gaps blocking "single source of truth"

1. **Three divergent task ledgers**, no reconciler; `owner_command_center` displays the wrong one
   (30 generic rows instead of the 8 real tasks).
2. `command_center/index.html:81` renders generated `state.js`, which is **stale** — it lists
   `BOARD-SYNC-01` / `DEDICATED-DID-01`, not the current `SUC-016` set.
3. **No runtime/API write path** for `tasks.json` — only offline scripts can write it.
4. `dev_tasks` — the only ledger with atomic claim / lease / heartbeat — is **0 rows** and **absent
   from every owner dashboard**.
5. `admin_tasks.db` is a checkout SQLite that does **not** route through `runtime_data_authority`
   and is **absent from the manifest**.
6. `data/owner_feed_events.jsonl` is an **unregistered store**.
7. **No single aggregator.** `owner_command_center`, `control_center`, `system_health` and
   `admin_dashboard` each read overlapping-but-different stores, so two surfaces can show different
   numbers for the same thing.
8. `interactions.jsonl` is `DUAL_WRITE_DRIFTED` (two writers).

---

## 4. "GitHub-repo-like structured platform" — what exists vs what does not

### Exists (CODE-PRESENT)
- **Versioned artifact registry** — `app/agents/harness/plugin_catalog.py`
  (`PluginManifest(version=…)`, 7 categories, `/api/admin/plugins`).
- **Revision-gated content lifecycle** — `app/marketing/creative_os/spec.py`
  (`SPEC_VERSION="1.0"`), `app/marketing/creative_os/approval.py`
  (exact-revision approval, `revision_mismatch` publish gate, `output_hash`),
  `states.py` (explicit state machine).
- **Agent registry** — `agent-os/` (31 agent `.md` + `standards/index.yml`).
- `frontend/explorer.html` (5194 lines) — a **static, hand-authored** architecture graph
  (4 tabs; live count via `/api/admin/plugins`). Not a data-driven repo browser.

### Does NOT exist
- Content **branches**, **commits**, **diffs**, **merge/revert**, or per-asset revision history.
- `branch_name` / `commit_hash` appear **only** in DevTask deploy evidence
  (`app/api/dev_tasks.py:82,341`) — there is no git-like model for tasks or content.

> The phrase "GitHub-repo-like structured platform" has **no existing implementation**. Any
> interpretation beyond the above is `UNKNOWN` and needs the owner to clarify what they mean.

---

## 5. Doc ↔ code contradictions (code wins)

1. `docs/coordination/CENTRAL_LEDGER.md:3-6` — "CANONICAL MACHINE SOURCE … Do NOT create a second
   ledger". `runtime_data_manifest.py` classifies `command_center.pilot_tasks` as
   `REBUILDABLE_CACHE` / `OFFLINE_TOOLING` (`durability_class: rebuildable`) — **and two more ledgers
   exist anyway.**
2. `CENTRAL_LEDGER.md:123` — `/app/bot-command-center` = `command_center/index.html` is CANONICAL.
   But `app/api/bot_command_center.py:145` actually serves `frontend/bot_command_center.html`, which
   `CENTRAL_LEDGER.md:125` itself calls **DEPRECATED**.
3. `CENTRAL_LEDGER.md:77` — "cycle #11, 31 ACTIVE, 39154 actions_today". The actual file reads
   **`NOT_INSTRUMENTED`, cycle 0, `active_workers=0`**.
4. `AGENTS.md:148`, `docs/HANDOFF_OWNER_COMMAND_CENTER.md:119`,
   `docs/context/WORKER_ROSTER.md:93` still describe `RUNNING_24_7_PARALLEL`. The file has since been
   remediated to `NOT_INSTRUMENTED` — **those docs are STALE.**
5. Manifest `MANIFEST_VERSION="2026-07-26.1"` vs allowlist `VERSION="2026-08-06.1"` — registry drift (PARTIAL).

> **Positive note:** the `workforce_live_status.json` truth-gate problem flagged earlier
> (`RUNNING_24_7_PARALLEL` with `active_workers=0`) has been **remediated to `NOT_INSTRUMENTED`**.
> The remaining problem is that five documents still assert the old false state.

---

## 6. What must be decided / done

**Owner decision (blocking):** which ledger is canonical?
- **Recommended:** `dev_tasks` (Postgres) — it is the only one with atomic claim, lease, heartbeat
  and reconcile, and it is already wired to 34 API routes. The other two become **read-only
  projections**: `tasks.json` for the Command Center UI, `admin_tasks.db` retired.

**Then, regardless of the decision (these are defects either way):**
1. `owner_command_center.py:191-206` must stop showing seed-like data as if it were real work.
2. `command_center/index.html:81` must stop rendering a stale generated `state.js`.
3. `admin_tasks.db` must route through `runtime_data_authority` and appear in the manifest — or be removed.
4. `data/owner_feed_events.jsonl` must be registered in the manifest.
5. `interactions.jsonl` dual-write must be resolved.
6. A single aggregator surface must be defined so two dashboards cannot report different numbers.
7. The five stale documents must be corrected (code wins).

**Not blocking, needs clarification:** what exactly the owner means by "GitHub-repo-like structured
platform" — the closest existing implementations are the plugin registry and the revision-gated
content lifecycle. A git-like model for content (branches/commits/diffs) does not exist and would be
new work.

---

*Evidence vocabulary: PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN.*
*All findings are CODE-PRESENT unless stated otherwise. No files were modified by this audit.*
