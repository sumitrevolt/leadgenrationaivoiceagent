# ADR-139 — Durable, multi-worker-safe harness audit & shadow-dedup backend

**Status:** Proposed (capability only; INERT by default, not activated) · **Date:** 2026-07-22

## Context

The canonical agent harness records shadow/enforcement evidence through
`app/agents/harness/audit.py:record()`, which appends to an append-only JSONL file
(`HARNESS_RUN_LOG`, default `data/harness_runs.jsonl`). Shadow dedup and enforce exactly-once
claims live in **module-level, process-local** state (`batch_shadow._SEEN`, `enforce._RESULTS` /
`_claim`). This is honest and simple, but it is **not multi-worker-safe**:

- Two Celery workers or two containers observing the same event each hold their own `_SEEN`/file,
  so a duplicate observation can append duplicate evidence.
- A process/container restart loses the in-memory dedup state.
- The file sink is filesystem-local (per container), so counts and replay are per-process.

Two production shadow canaries (`dag_engine`, `batch_harness`) have proven the bounded shadow path,
but production-grade multi-worker enforcement/observation needs a durable, atomic backend.

## Decision

Add a durable backend abstraction (`app/agents/harness/audit_backend.py`) selected by
`HARNESS_AUDIT_BACKEND` (default `jsonl`):

- **`jsonl` (default):** byte-identical to today — append-only file, no record-layer dedup. Dev/test
  and the current production baseline. Production behaviour is **unchanged** until an operator
  explicitly opts in.
- **`redis` (production-grade):** atomic first-observer-wins dedup via `SET NX PX` on
  `harness:audit:dedup:<key>`, plus a durable, retention-bounded Redis **Stream**
  (`harness:audit:events`, `XADD MAXLEN ~`) as the audit-of-record. Multi-worker- and restart-safe.
  Best-effort counters (`harness:audit:counts` hash) power the status surface.

Redis was chosen (option 1 in the brief) because the project **already** uses Redis as the
authoritative, fail-closed idempotency and kill-switch store (`harness/stop.py`, agent-runtime
idempotency). Reusing it introduces **no new external service** and matches the existing reliability
posture. The write path is centralised in `audit.record()` (single choke-point) rather than scattered
across the five family adapters.

### Rejected alternatives

- **PostgreSQL append-only table (option 2):** durable and queryable, but adds an Alembic migration
  and couples the hot observe path to the primary OLTP DB. Deferred; can be added later as a second
  sink if long-term analytical retention is required.
- **Hybrid Redis-dedup + Postgres-audit (option 3):** strongest long-term, but larger blast radius
  than justified for the first durable step. The Redis Stream already gives durable, ordered,
  retention-bounded storage; Postgres can be layered later without changing the seam.

## Production semantics

- **Atomic dedup key** (`derive_dedup_key`) is derived from: deployed SHA (`APP_VERSION`), source
  family/loop, agent, tenant, canonical tool + version, run id, node/item id, attempt, and kind. Same
  logical observation across processes/containers/restarts → one key; different attempts and different
  legitimate events stay distinct.
- **Fail-closed:** in `redis` mode, if Redis is unreachable the observation is **dropped** and an
  operational error is emitted (`backend_errors` counter + `logger.error`). It **never** silently
  reverts to process-local dedup or the local file. The trade-off is explicit — we lose *evidence*
  rather than *claim dedup safety we cannot provide*.
- **Evidence-only dedup:** this dedups the audit/shadow **evidence**. It makes **no** claim of
  exactly-once **business** execution — the legacy path stays authoritative and is never re-run or
  altered by the audit layer. A harness observation failure never changes the legacy result.
- **Retention:** dedup TTL `HARNESS_DEDUP_TTL_S` (default 14 days, > operational review window);
  stream capacity guard `HARNESS_AUDIT_MAXLEN` (default 1,000,000, approximate). No unbounded keys.
- **Size + sanitisation:** `HARNESS_AUDIT_MAX_BYTES` (default 16 KiB); oversized rows truncate the
  heavy `legacy_result_summary` then hard-cap to bounded identity fields. Forbidden-looking keys
  (password/secret/token/authorization/api_key/cookie/private_key/dsn) are redacted at the sink
  (defence-in-depth over the observe-layer redaction). Never stores credentials, raw customer
  payloads, private message bodies, full env, or unbounded model output.

## Migration of the two historical records

The production JSONL currently holds **2** valid records (dag=1, batch=1; checksum
`660fdb599092bed637773887a096d758509c41f86ad09d88e3a15e6bf4f5999e`). Two options are documented; the
choice is made at activation time by the owner, not by this change:

- **Option A — idempotent import:** import both records into the durable backend exactly once
  (dedup keys make re-import a no-op), storing the source checksum; original JSONL left immutable.
- **Option B — baseline boundary:** leave JSONL immutable as historical evidence; durable storage
  starts at 0 with a recorded cutover timestamp; combined logical baseline = 2.

Neither silently loses nor double-counts evidence. `tests/test_harness_audit_backend.py` proves the
Option-A import is idempotent.

## Consequences

- Additive, inert-by-default; zero production change until `HARNESS_AUDIT_BACKEND=redis` is set
  (separate owner authorization + deploy).
- `harness.status` now reports `audit_backend` (type, health, counts, duplicates_suppressed) with no
  secrets. Owner OS remains the sole mutation authority.
- Deployment installs **capability only**. Activation and historical migration require separate owner
  authorization and are out of scope for the introducing PR.

---

## Addendum (2026-07-22) — atomicity, durability proof, and retention contract

### Atomic claim + append (single Lua script)

The dedup **claim** and the durable **append** are performed in one `EVAL` — never two
independent round trips. `_ATOMIC_LUA` (in `audit_backend.py`):

```
GET dedup_key -> if present: HINCRBY duplicates_suppressed; return {DUPLICATE, stored_value}
XADD stream MAXLEN ~ N * e <event>          -> id
SET dedup_key '{"event_id":id,"envelope":<env>}' PX ttl
HINCRBY records_created / family:* / mode:*
return {CREATED, stored_value}
```

Because a Redis script runs atomically:
- **XADD failure aborts the whole script** — the dedup key is never committed, so a retry recreates
  the event (no dedup key stranded without a durable record).
- **Client timeout after a successful commit** is safe — the retry finds the dedup key and returns
  the original `event_id` (no second stream record).
- **Concurrent observers** — exactly one creates the stream event; all others get `DUPLICATE` with
  the same id.

### Cluster-safe key design

All keys the script touches share one hash tag `{audit}` → one slot:
`harness:{audit}:events` (stream), `harness:{audit}:dedup:<sha256[:32]>`, `harness:{audit}:metrics`.
Key names carry only bounded hashes — never raw tenant/agent/tool/payload values.

### Retention ↔ dedup consistency (Option A)

The dedup TTL (14 d) can outlive a count-trimmed stream record (`MAXLEN ~ 1,000,000`). To prevent a
"dedup says duplicate but the event is gone" state, the dedup **value stores a compact immutable
envelope** (identity + verdict fields) alongside the `event_id` (`derive_envelope`). A duplicate
replay is therefore always resolvable from the dedup value itself, independent of stream trimming.
The stream remains the full durable audit-of-record; the envelope is the bounded dedup backstop.

### Durability proof (production Redis `leadgen_redis`)

Verified read-only 2026-07-22 on the intended service (`redis:7-alpine`, redis 7.4.9):
`appendonly=yes`, `appendfsync=everysec`, RDB `save 3600 1 300 100 60 10000`, `maxmemory=256MB`,
**`maxmemory-policy=noeviction`**, `dir=/data` on the persistent named volume `leadgen_redisdata`,
`aof_enabled=1`. This **meets** the durable-audit posture: a container/Redis restart preserves the
stream and dedup keys, and audit records cannot be silently evicted under memory pressure — writes
fail closed instead (the required behaviour). `EVAL`/Lua is supported. No separate Redis or Postgres
is required. (Capacity note: at harness shadow volume, 256 MB with `noeviction` is ample headroom;
under pressure writes fail closed rather than lose evidence.)

### Failure & recovery matrix (proven)

| scenario | result |
|---|---|
| Redis unavailable before script | fail-closed dropped observation + operational error; legacy result untouched |
| script/connection error | fail-closed; `script_errors` incremented; **nothing committed** (atomicity) |
| client timeout after commit | retry finds dedup key → returns original `event_id`; no second record |
| process crash after commit | record durable in stream + dedup; a later retry resolves as duplicate |
| Redis restart | AOF/RDB + volume preserve stream & dedup |
| duplicate replay before TTL | `DUPLICATE` with original id |
| duplicate replay after TTL | treated as new (documented; TTL ≫ review window) |
| stream trimmed | dedup envelope still resolves the duplicate (Option A) |
| maxmemory reached | `noeviction` → write fails closed (no silent audit loss) |

Real-Redis, real-multiprocess (8 OS processes) validation of the atomic path: **1 record created, 7
duplicates, 1 distinct event id, 0 partial commits on induced failure** — see
`tests/test_harness_audit_backend_integration.py` (skips without a live Redis; run with
`HARNESS_TEST_REDIS_URL`).

### Metrics

Durable in the `metrics` hash: `records_created`, `duplicates_suppressed`, `backend_errors`,
`script_errors`, `oversize_rejections`, plus `family:*` / `mode:*`. Status also derives
`stream_length`, `dedup_keys_active` (bounded scan), and oldest/newest event ids. `backend_errors`
that occur while Redis is entirely unreachable are unavoidably process-local (logged) and labelled as
such — durable counters require a reachable backend.

---

## Amendment 2 (2026-07-22) — one authoritative all-or-nothing write

The earlier `XADD`+`SET`+`HINCRBY` Lua script was **not** all-or-nothing: Redis does
not roll back a script's earlier writes when a later command errors. Reproduced on
an isolated Redis by poisoning the metrics key to a non-hash — the `HINCRBY` raised
`WRONGTYPE` **after** `XADD` and `SET` had already committed (stream_length=1,
dedup key present) while the client saw an error. Evidence and dedup could disagree.

**Corrected model.** Each observation is a single immutable **record key**:

```
SET harness:{audit}:record:<sha256> <value> NX GET PX <retention>
```

That one command is the durable audit record, the first-observer claim, the
duplicate identity, and the replay envelope. `nil` → created; old value → duplicate
(the returned value *is* the record); error → nothing created. No second structure
establishes durability, so a partial commit is impossible. Validated on real Redis 7.

**Record value** (`build_record`): `{event_id, event (sanitized), envelope (compact),
source_app_version, created_at}`. `event_id` is deterministic (== dedup key).

**Stream + metrics are now DERIVED, non-authoritative indexes** updated best-effort
*after* the authoritative write. If they fail, the record still exists, `counts()`
reports `index_lag`/`index_errors`, and `RedisBackend.reconcile(dry_run=…)` rebuilds
them from the authoritative records (idempotent; never touches records; supports
dry-run). `counts().total` is the authoritative record-key count, not the stream.

**Retention = dedup lifetime.** One key holds both, so "dedup without record" and
"record without dedup" cannot occur. `HARNESS_AUDIT_RETENTION_S` default **90 days**
(no shorter dedup TTL). After expiry a replay is legitimately a new observation.

**Strict configuration.** `HARNESS_AUDIT_BACKEND` resolves by exact match: unset/empty
or `jsonl` → jsonl; `redis` → redis; **any other value** (typo, trailing space, wrong
case) → **invalid** → unhealthy, writes fail closed, **never silently jsonl**. Status
reports `configured_value`, `resolved_backend`, `configuration_valid`, and honest
`selected_intentionally` / `fallback_active` / `durable` / `multi_worker_safe`.

**Migration provenance.** `derive_dedup_key(row, source_app_version=…)` lets a
migration identify historical events under their ORIGINAL deployed SHA
(`878c1397…`), never the migrating process's runtime SHA. Live observations keep
using the current runtime SHA. The guarded CLI is `python -m
app.agents.harness.audit_migrate` (dry-run default; `--apply` requires
`--approval-token`, `--expected-source-checksum`, `--source-app-version`; idempotency
marker keyed on source checksum + source SHA + schema + namespace; a different
checksum under the same identity is refused; the source file is never modified).
Migration and backend activation remain two independent owner-authorized operations.
