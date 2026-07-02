---
name: db-migration-safety
description: Postgres schema-change safety on live prod — expand-contract pattern, PgBouncer gotchas, additive-only default, backfill via worker, rollback plan, dormant-column policy. Use jab koi table/column/index add-change-drop ho, data backfill chahiye, ya "DB change deploy kaise karu bina downtime" poochha jaye.
---

# DB Migration Safety (schema change = one-way door, respect karo)

> Enterprise audit skill. Live Postgres (PgBouncer :6432) + paying-customer path. **House pattern = additive-first** (razorpay_* columns dormant-kept = iska example). Pehle `context-first`.

## Rules (single-VPS live-DB reality)
1. **Additive default**: naya column NULLABLE ya DEFAULT ke saath — old code + new code dono chalein (deploy window me dono versions zinda hote hain).
2. **Expand-contract for renames/type-change**: naya column add → dual-write code ship → backfill (worker job, batched) → read switch → purana column DORMANT chodo (drop = alag PR, hafte baad, backup ke baad).
3. **DROP/DESTRUCTIVE = 3 gates**: (a) fresh `pg_backup.sh` manual run + verify, (b) column 7+ din dormant with zero reads (grep + pg_stat check), (c) rollback SQL likha hua ready.
4. **PgBouncer gotchas**: transaction-pooling mode me session-level state (advisory locks, SET, LISTEN) unreliable — migration DIRECT Postgres :5432 pe chalao container me, app-time queries pooler pe.
5. **Index on live table**: `CREATE INDEX CONCURRENTLY` (lock nahi) — aur yeh transaction me NAHI chal sakta, akela statement.
6. **Backfill**: KABHI web process me nahi (prod-down lesson) — Celery task, batch 500-1000 rows, sleep between, idempotent (resume-safe), progress log.
7. **App-code + migration same deploy me couple mat karo** jab avoid ho sake: migration pehle (backward-compatible), code baad me.

## Migration loop
1. `context-first`: model/table ke SAARE readers/writers grep (`grep -rn "table_name\|ColumnName" app/`), including raw SQL + exports + backups scope.
2. Migration SQL + rollback SQL dono likho (rollback untested = rollback nahi hai).
3. Local/scratch test: dump ka scratch restore (dr-restore-drill ka step 2 reuse) pe migration chalao — timing note karo (5s vs 5min = lock impact).
4. Prod: backup fresh → migration direct :5432 → verify (`\d table`, row spot-check) → app deploy → `/verify` + targeted tests.
5. Evidence SESSION_LOG me: kya change, timing, rollback path.

## Rollback plan (pehle likho, kabhi use na ho best case)
- Additive change = rollback trivial (naya column ignore hota old code se).
- Contract/destructive = rollback SQL + agar data-loss window bana to pg dump se selective restore.
- Nuclear: SQLite `/opt/leadgen/leadgen.db` rollback-backup = LAST resort (stale hoga — sirf total-loss scenario).

## Enterprise bar
- Har migration reversible ya explicitly documented one-way (approval ke saath).
- Zero-downtime default; maintenance-window sirf exception with user heads-up.
- Schema drift check: prod `\d` vs models code — quarterly.

## Output
Migration + rollback SQL pair · scratch-test timing evidence · reader/writer touchpoint list · post-deploy verify green.

## Related repo skills
`context-first` (touchpoint sweep) · `dr-restore-drill` (scratch restore + backup gate) · `verify-ship` (deploy loop) · `leadgen-infra-doctor` (PgBouncer) · `api-design` (contract-first).
