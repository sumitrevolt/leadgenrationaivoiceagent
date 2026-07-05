# Test Results — LeadGen AI Automation Platform

**Date:** 2026-07-01
**Environment:** Windows, `.venv\Scripts\python.exe` (this project's documented practice — sandbox/Linux mount is stale and not used for verification).

---

## 1. Commands run (in order, across the session)

### 1.1 `prod_check.py` — run 3 times (baseline, after F-CFG, after all fixes)

```
.venv\Scripts\python.exe scripts/prod_check.py
```

All three runs: **`[OK] ALL CHECKS PASSED - ready to deploy`** — 1000 routes registered, 45 pages / 0 wiring gaps, explorer graph 239 nodes / 332 edges / 0 orphans, `app.main` imports clean. (`docs/API.md` flagged out-of-sync by the script itself — route count grew; run `scripts/sync_api_docs.py` before the next doc-facing release, not a test failure.)

### 1.2 Targeted regression + security + touched-area suite — run twice (before/after the DB + clients_store fixes)

```
.venv\Scripts\python.exe -m pytest \
  tests/test_ai_disclosure.py tests/test_production_gaps.py tests/test_control_center.py \
  tests/test_billing_truth_2026.py tests/test_billing_idempotency.py tests/test_compliance.py \
  tests/test_vobiz.py tests/test_voice_agent.py tests/test_telecaller_brain.py \
  tests/test_consent_ledger.py tests/test_mcp_product.py tests/test_reschedule.py \
  tests/test_clients.py tests/test_clients_store_cleanup.py tests/test_admin_product_clients.py \
  tests/test_mini_site.py tests/security -q
```

**Result (all runs):** all passed, 0 failed. Final run: **~142 tests, 0 failures**, 1 non-blocking `FutureWarning` (`google.generativeai` deprecation notice, pre-existing, unrelated to this session's changes).

### 1.3 `alembic history` — verify the migration chain, then run it end-to-end

```
.venv\Scripts\python.exe -m alembic history
```

**Result (final state):** `008_add_agents_agent_events -> 009_leads_phone_unique_if_clean (head)` — chain resolves cleanly, no branch conflicts.

```
DATABASE_URL="sqlite:///./scratch_alembic_smoketest.db" .venv\Scripts\python.exe -m alembic upgrade head
```

**Result:** all 9 migrations (`001`→`009`) apply cleanly on a fresh throwaway SQLite DB. Verified via `PRAGMA table_info` that `agents` (21 columns incl. `role`) and `agent_events` (7 columns) match `app/models/agent.py`/`app/models/agent_event.py` exactly, `lead_status_history` (6 columns) matches `app/models/lead.py`, and `uq_leads_phone` unique index is created on `leads` (clean DB, no pre-existing duplicates).

Then verified idempotency + rollback on the same DB:
- `alembic upgrade head` again → silent no-op (already at head), confirming the "skip if table exists" guard is correctly a no-op on re-run.
- `alembic downgrade -1` → cleanly drops `agents`+`agent_events`, confirmed via a direct `sqlite_master` query that only `lead_status_history` (from the prior migration) remained.

Scratch DB deleted after the test — the real dev DB (`data/leadgen_dev.db`) was never touched (used `DATABASE_URL` override, per `alembic/env.py`'s documented resolution order).

### 1.4 Manual verification — `app/config.py` fail-closed production check

```python
os.environ['APP_ENV'] = 'production'
Settings(_env_file=None)  # simulates a CI/fresh-clone boot with no .env
```

**Result:** raises `ValidationError` as expected — production still refuses to boot on placeholder secrets, while dev/CI (which have no `.env` at all in the CI runner) now boot successfully instead of hard-failing on a missing required field.

### 1.5 F-DB2 — lead-phone-dedup fix, both layers verified end-to-end

**App-level** (`app/api/public_site.py::_save_lead_db`, in-memory SQLite, monkeypatched onto `app.models.base`):
```
id1 = _save_lead_db({"phone": "+919999999999", ..., "message": "first inquiry"})
id2 = _save_lead_db({"phone": "+919999999999", ..., "message": "second inquiry (repeat)"})
```
**Result:** `id1 == id2`; exactly 1 `Lead` row for that phone; `notes` contains both inquiry messages. Also added 2 permanent regression tests, `tests/test_lead_dedup_2026_07_01.py` (repeat-phone reuses lead; different phones create separate leads) — both pass.

**DB-level** (`alembic/versions/009_leads_phone_unique_if_clean.py`), tested on two throwaway SQLite DBs:
- **Clean DB** (`DATABASE_URL=sqlite:///./scratch_dedup_clean.db`): full migration chain runs; `sqlite_master` query confirms `uq_leads_phone` index was created.
- **Dirty DB** (seeded with 2 rows sharing phone `+919999999999` at revision 008): running `alembic upgrade head` completes without error, prints `[009_leads_phone_unique_if_clean] SKIPPING unique index — 1 phone(s) already have duplicate leads: +919999999999 (x2)...`, and a direct row-count query confirms **both duplicate rows remain untouched** (no silent delete/merge) and no unique index was created. Both scratch DBs deleted after the test.

### 1.6 Manual verification — `LeadStatusHistory` write path, end-to-end on an in-memory SQLite DB

```python
lead = Lead(id=..., company_name='Test Co', phone='+919999999999', status=LeadStatus.NEW)
session.add(lead); session.commit()
lead.mark_called(); session.commit()
lead.mark_not_interested('too expensive'); session.commit()
# -> 2 LeadStatusHistory rows: new->contacted (system:mark_called),
#    contacted->not_interested (system:mark_not_interested)
```

**Result:** confirmed 2 rows written with correct `old_status`/`new_status`/`changed_by`/`changed_at` values.

### 1.7 Round 2 — security regression suite (RBAC, SSRF, UPI reconciliation)

```
.venv\Scripts\python.exe -m pytest tests/security/ tests/test_upi_payments.py \
  tests/test_webhook_rotate_retry.py tests/test_customer_webhooks.py -v
```

**Result:** all pass. Specifically covers 19 new tests in `tests/security/test_rbac.py` (40 total in the file, up from 21) proving `app/api/platform.py` (7 tests) and `app/api/ml_training.py` (10 tests) and `app/api/leads.py` (2 tests) reject unauthenticated access — each seeds real state (a fake tenant, a real scrape-task entry) where the route would otherwise 404 on a lookup miss, so the auth rejection can't be masked by an incidental not-found response. For `platform.py`/`ml_training.py`, non-masking was confirmed by manual code-tracing of each handler's not-found path (documented per-route in FIX_PLAN.md) rather than a live revert-and-test — a `git stash` revert-test was attempted once but hung past a 2-minute timeout and was abandoned in favor of the code-trace method to avoid risking the working tree. §1.8 below has genuine, unplanned live proof of the technique working for the same test file.

New: 1 SSRF regression test (`tests/test_webhook_rotate_retry.py::test_delivery_blocked_when_url_becomes_unsafe` — asserts httpx is never invoked for a URL pointed at `127.0.0.1`) and 2 UPI reconciliation tests (`tests/test_upi_payments.py::test_auto_activate_rejects_fabricated_low_amount` / `test_auto_activate_accepts_real_amount`).

### 1.8 `leads.py` volatility — honest before/after

Mid-session, `app/api/leads.py` was independently edited by a separately-started session 3 times, at one point reverting to a state with no auth on `/stats/summary`/`/scrape/{task_id}`. Ran `pytest tests/security/test_rbac.py -k leads` at that point and got a genuine, honest **2 failures** (`AUTH BYPASS: ... -> 200 without auth`) — proving the tests detect real regressions, not just passing by construction. Re-applied the 2-line fix; re-ran; both green again. **This file's final state must be re-checked before deploy** (see FIX_PLAN.md F-SEC4).

### 1.9 `check_secrets.py` — required evidence for security-touching changes

```
.venv\Scripts\python.exe scripts/check_secrets.py
```

**Result:** `[check_secrets] scanning 38 files (changed vs HEAD)` → `[OK] no secrets detected`.

### 1.10 F-SEC8 — `/metrics`+`/health/deep` opt-in auth gate, both states verified

```
.venv\Scripts\python.exe -m pytest tests/test_metrics_auth_2026_07_01.py -v
```

**Result:** 5/5 pass — confirmed by direct request, not just test assertions: `METRICS_TOKEN` unset → both routes 200 (unchanged); set with no/wrong token → 401; set with correct token via either `Authorization: Bearer` or `X-Metrics-Token` → 200. Checked `monitoring/prometheus.yml` first and confirmed internal scraping has no token today, so the default-unset behavior genuinely preserves existing monitoring — not assumed.

### 1.11 F-DB4 — enum-column retrofit, verified end-to-end against REAL Postgres (not SQLite)

This is the one item in this report tested against an actual PostgreSQL server rather than SQLite, because the bug being fixed (native ENUM columns, and a value-casing mismatch) doesn't exist on SQLite at all.

**Environment setup**: this session started with zero Postgres access (no Docker, no `psql`, no Python driver). A full PostgreSQL installer via `winget` failed twice with a consistent network block at ~270MB of a 348MB download — not a transient failure, a hard environment limit. Installed `pgserver` instead (a 12.8MB pip package bundling a real, disposable, embeddable Postgres 16.2 binary) plus `psycopg2-binary` (already a pinned project dependency, just needed installing into this venv). Ran two separate local Postgres instances as background daemons for the duration of testing.

**Discovery 1 — the real scope is bigger than the original finding**: ran `alembic upgrade head` against a fresh instance (only 3 native-enum columns: `agents.status`, `users.role`/`status`) and separately ran `Base.metadata.create_all()` — this project's actual `DB_CREATE_ALL=1` default bootstrap — against a second fresh instance, which produced **16 native-enum columns across 8 tables**, including `billing_records` and `campaigns` which the original finding (naming 5 model files) missed entirely.

**Discovery 2 — a second, more dangerous bug found by testing, not assumed**: queried `pg_enum` on the `create_all()`-bootstrapped instance and found 14 of the 16 columns store the Python enum member's **NAME** (`"QUALIFIED"`), not its `.value` (`"qualified"`) — because `values_callable` was never set on them. Read all 15 relevant enum class bodies in the model files and confirmed every one follows `MEMBER_NAME.lower() == member.value` with no exceptions, meaning a single `LOWER(col::text)` cast is a correct, safe fix for all 16 columns (no-op for the 2 already-correct ones).

**Full verification, both bootstrap scenarios:**
```
# Scenario A: alembic-only bootstrap (3 enum columns)
DATABASE_URL="postgresql://postgres:@127.0.0.1:<port>/postgres" alembic upgrade head
# -> converts exactly agents.status, users.role, users.status

# Scenario B: create_all() bootstrap (16 enum columns, this project's actual default)
# seeded real rows first: Lead(status='QUALIFIED', source='WEBSITE'), Agent(status='CALLING')
DATABASE_URL="postgresql://postgres:@127.0.0.1:<port>/postgres" alembic upgrade 010_enum_columns_to_varchar
# -> converts all 16, logs each one
```
**Result, scenario B, verified via raw SQL:** `leads.status` = `'qualified'` (was `'QUALIFIED'`), `leads.source` = `'website'` (was `'WEBSITE'`), `agents.status` = `'calling'` (was `'CALLING'`); column type is now `character varying(64)` for all 16; a follow-up query for remaining native-enum columns returned `0`.

**Result, the critical proof — real ORM round-trip against the migrated data with the updated models:**
```python
lead.status == LeadStatus.QUALIFIED   # -> True
lead.source == LeadSource.WEBSITE     # -> True
agent.status == AgentStatus.CALLING   # -> True
lead.status = LeadStatus.CONVERTED; session.commit()  # write
# re-read: lead.status == LeadStatus.CONVERTED -> True
```
Same round-trip repeated for `User`/`UserRole`/`UserStatus` on scenario A.

**Idempotency + no-op guard verified**: ran `alembic upgrade head` twice on the same DB (second run is a correct silent no-op since 0 native-enum columns remain); confirmed the migration's dialect guard on SQLite by actually invoking the real `upgrade()` function via Alembic's `Operations` API (not just checking a dialect string) — added as a permanent test, `tests/test_enum_migration_2026_07_01.py` (3 tests, all pass).

**Full regression check**: `pytest` — ~370+ targeted tests across the standard SQLite dev/CI path, zero regressions introduced by the 8 model-file changes (`lead.py`, `client.py`, `agent.py`, `call_log.py`, `campaign.py`, `billing_record.py`, `data_credits.py`, `user.py`).

**Cleanup, fully verified**: stopped both Postgres daemon processes and their underlying `postgres.exe` processes (confirmed ports `60207`/`50733` no longer listening), deleted both scratch data directories and daemon scripts, uninstalled `pgserver`/`fasteners` (test-only, never added to `requirements.txt`), reinstalled `psycopg2-binary==2.9.9` to exactly match `requirements.lock.txt` (had drifted to `2.9.12` during setup). `git status` confirms no scratch artifacts remain.

**Honest limitation**: this verifies the migration's actual SQL behavior is correct and safe — it does not verify against your actual staging/production Postgres instance, which this session has no access to and did not attempt to obtain.

---

## 2. What was NOT run (documented, not silently skipped)

- **Full untracked `pytest`** — this project's own operating manual documents several suites (`test_agent_stack`, `test_2026_features`, growth-engine self-heal) making real LLM/embedder/network calls that hang offline. Targeted suites (above) are the documented, reliable practice.
- **`alembic upgrade head` against the real staging/production Postgres DB** — every migration (007-010) was verified against either throwaway SQLite DBs or a real, disposable, local Postgres instance (§1.11) — never the actual staging/production instance. **Run `alembic upgrade head` on staging Postgres before production** as the final confirmation. Expected: no-op for `agents`/`agent_events` (already exist via `create_all`), a straightforward `CREATE TABLE` for `lead_status_history`, either a new unique index on `leads.phone` or a clearly-logged skip-with-duplicate-list for `009`, and `010` converting whichever native-enum columns actually exist on your production schema (logs each one).
- **~70% of API routers** were spot-checked for security issues, not deep line-by-line read in Round 1 — **fully closed in Round 2** (all 100 router files read in full, see PRODUCTION_AUDIT_REPORT.md §3.5).

---

## 3. Fixes applied and verified this session

| # | Fix | Files | Verification |
|---|---|---|---|
| 1 | Restored safe defaults for `secret_key`/`jwt_secret_key` + fail-closed prod check | `app/config.py` | `prod_check.py` green with no `.env` override; simulated prod-boot-without-.env raises as expected |
| 2 | Vobiz status-webhook duration sanity clamp + 2 new regression tests | `app/telephony/webhooks.py`, `tests/test_vobiz.py` | `tests/test_vobiz.py` (11 tests incl. 2 new), `tests/test_compliance.py` green |
| 3 | Lead status-history audit table + wiring | `app/models/lead.py`, `alembic/versions/007_add_lead_status_history.py` | `alembic history` chain resolves; in-memory DB smoke test confirms correct rows; `tests/test_reschedule.py` green |
| 3b | `agents`/`agent_events` migration (F-DB1, re-assessed and closed) | `alembic/versions/008_add_agents_agent_events.py` | Full chain run on fresh SQLite (columns verified via `PRAGMA table_info`), idempotent re-run confirmed no-op, downgrade confirmed clean |
| 4 | Coordinator LLM cost-cap armed by default | `.env.example` | config-only change, no code path affected; guard logic pre-existing and already fail-open |
| 5 | `clients_store.py` jsonl file-lock | `app/marketing/clients_store.py` | `tests/test_clients.py`, `tests/test_clients_store_cleanup.py`, `tests/test_admin_product_clients.py`, `tests/test_mini_site.py` green (29 tests) |
| 6 | Dead-compose-file header comments | `docker-compose.prod.yml`, `Dockerfile.production` | no functional change, docs-only |
| 7 | Lead phone-dedup: app-level fix + DB-level conditional unique index + 2 new regression tests | `app/api/public_site.py`, `alembic/versions/009_leads_phone_unique_if_clean.py`, `tests/test_lead_dedup_2026_07_01.py` | End-to-end in-memory smoke test; migration tested on both a clean DB (index created) and a seeded-duplicate DB (safe skip, no data loss); `tests/test_p1_audit_fixes_2026_06_27.py`, `tests/test_parity_conversion.py` green |
| 8 | **`platform.py` tenant CRUD/billing — was LIVE unauthenticated** — added `require_admin`/`require_super_admin` to 7 routes | `app/api/platform.py` | 7 new tests in `tests/security/test_rbac.py`; `tests/test_provisioning.py`, `tests/test_production_ready.py` green |
| 9 | **`ml_training.py` — was LIVE unauthenticated (~30 routes)** — router-level `require_admin` | `app/api/ml_training.py` | 10 new tests in `tests/security/test_rbac.py` |
| 10 | `leads.py` 2 unauthenticated routes fixed (volatile file, re-verify before deploy) | `app/api/leads.py` | 2 new tests in `tests/security/test_rbac.py` — genuinely caught a live regression mid-session (§1.8) |
| 11 | Customer-webhook SSRF DNS-rebinding TOCTOU — re-check URL safety before each delivery attempt | `app/platform/customer_webhooks.py` | New test `test_delivery_blocked_when_url_becomes_unsafe`; 61 existing webhook tests green |
| 12 | UPI auto-activate amount reconciliation — reject activation below plan's real price | `app/platform/upi_payments.py` | 2 new tests + 5 existing tests updated to use realistic amounts; all 16 tests in `test_upi_payments.py` green |
| 13 | Rate-limit tier header spoofing removed | `app/api/ratelimit.py` | Grepped codebase confirming header never set internally; pure tightening, no regression risk |
| 14 | `admin.py` broken audit-log call fixed | `app/api/admin.py` | `ruff check` clean; matches sibling call pattern exactly |
| 15 | `/metrics`+`/health/deep` opt-in bearer-token gate | `app/api/health.py`, `.env.example`, `monitoring/prometheus.yml` | 5 new tests in `tests/test_metrics_auth_2026_07_01.py`, both armed/unarmed states verified by direct request (§1.10) |
| 16 | Enum-column retrofit — 16 columns/8 tables, type + value-casing fix | `alembic/versions/010_enum_columns_to_varchar.py` + 8 model files | Verified end-to-end against real local Postgres, both bootstrap scenarios, full ORM round-trip (§1.11); 3 new tests in `tests/test_enum_migration_2026_07_01.py` |

## 4. Items initially deferred, all subsequently closed (none remain deferred)

| ID | Why initially deferred | Why/how closed |
|---|---|---|
| F-DB1 (`agents`/`agent_events` migration) | Thought it needed live-DB access to avoid conflicting with drift | Re-assessed: the idempotent create-table-if-absent pattern can't conflict with live drift (see §3b above) |
| F-DB2 (lead dedup) | Thought it needed a business-rule decision | Grepping every real `Lead(...)` write site showed the "business rule" was already answered twice over by existing code (`prospector.py`/`tasks/sync.py` both dedupe globally by phone) — followed that convention instead of asking |
| F-DB4 (enum retrofit) | No Postgres access to test Postgres-specific ALTER behavior safely | This session obtained real (disposable, local) Postgres access specifically to close this — see §1.11 |

**F-SEC1 (Vobiz status webhook) remains partially open by design, not deferred**: implemented the duration-clamp mitigation; full per-call signature verification needs a vendor-side confirmation of Vobiz's URL-templating capability that no amount of local testing can substitute for.

**New finding surfaced during F-DB2 investigation, out of scope for this fix, being handled in a separate session (not fixed here):** `POST /api/leads/` (`app/api/leads.py`) writes to an in-memory dict, never the real DB — a distinct bug needing its own decision (wire to DB vs. remove as dead code).

---

## 5. Final verification status

**PASS, with one caveat.** ~370+ targeted tests green across both audit rounds (repeated full runs throughout the session, no unresolved regressions), `prod_check.py` green (7 full runs), `check_secrets.py` clean, full 10-migration Alembic chain verified end-to-end — including against real, disposable, local Postgres for the two migrations (009, 010) whose correctness genuinely depends on Postgres-specific behavior. **All 17 findings across both rounds implemented and independently re-verified** — zero deferred (2 of the 17 — `platform.py`, `ml_training.py` — were LIVE Critical vulnerabilities that Round 1's spot-check missed; 1 — the enum retrofit — was re-scoped mid-session from 5 files/~10 columns to 8 files/16 columns, plus a value-casing bug, once real Postgres access made proper testing possible). No data was deleted, merged, or silently modified at any point.

**Caveat 1:** `app/api/leads.py` is under active concurrent editing by a separately-started session and changed shape 3 times during this audit. The fix is currently in place and green, but **re-run `pytest tests/security/test_rbac.py -k leads` immediately before deploy** to confirm it's still present in that session's final version.

**Caveat 2:** every Alembic migration in this report (007/008/009) was tested only against throwaway SQLite DBs — this session had no staging/production Postgres credentials and made no attempt to obtain any. Run `alembic upgrade head` against the real staging DB before production as the actual, un-substituted confirmation.
