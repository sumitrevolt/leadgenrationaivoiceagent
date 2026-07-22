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
