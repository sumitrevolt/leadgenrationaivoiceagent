# GAP REGISTER — living tracker (seeded 2026-07-05)

> **Kya hai:** `docs/SYSTEMATIZATION_AUDIT_2026_07_05.md` ke saare gaps ka LIVING tracker.
> Status YAHAN update hota hai (audit doc frozen snapshot hai). Har fix apne phase ki approval pe.
> Rules: surgical-only (additive/flag-gated), har item = alag commit, verify gates green
> (`prod_check.py` + `check_secrets.py` + targeted pytest), full pytest KABHI nahi (team_pulse hang).
> **2026-07-05 shaam:** user "sab karo" → Phase 2 + Phase 3 safe-items same-day executed (PR #28).

**Status values:** `OPEN` · `IN-PROGRESS` · `DONE (sha)` · `USER-CONFIRM` (owner decision chahiye) · `WONT-FIX (reason)`

## Phase 1 — zero-behaviour-change hygiene ✅ (2026-07-05)

| ID | Gap | Risk | Status |
|---|---|---|---|
| R-01 | 6 registry-invisible flags (`LLM_COUNCIL`, `CUSTOMER_OFFICE`, `ADMIN_OFFICE`, `SESSION_MEMORY`, `DLT_APPROVED`, `PROMETHEUS_HTTP_METRICS`) | LOW | DONE (e30e6f8) |
| R-02 | Static route-collision guard (flag-OFF mounts CI-invisible the) | LOW | DONE (7404918 — `scripts/route_collision_audit.py`, 1062 static vs 1030 runtime, prod_check-wired) |
| R-03 | `.env.example` dead keys + critical undocumented | LOW | DONE (41e2e11) |
| R-04 | 3 competing doc indexes → HANDOFF.md master | LOW | DONE (188cced) |
| R-05 | Root stale reports → `docs/archive/` | LOW | DONE (188cced/7566920; TASKS.md WONT-FIX — active skill-workflow surface) |

## Phase 2 — guards + consolidation ✅ mostly (2026-07-05 "sab karo")

| ID | Gap | Status |
|---|---|---|
| R-10 | ENV reference autogen | DONE (7b90624 — `scripts/env_reference_sync.py` + `docs/ENV_REFERENCE.md` 582 keys + prod_check INFO line) |
| R-11 | `tests.yml` overlap demote | **OPEN — owner-blocked:** pehle GitHub → Settings → Branches me required status-checks verify karo; `test` job required nikla to demote merges block karega. (Note: tests.yml apna httpx-pin rakhta hai aur 10-file fast-signal deta hai — demote optional hai) |
| R-12 | deploy-vps pytest `continue-on-error` → hard gate | OPEN — ci.yml tests job PR #28 pe GREEN hone ke BAAD flip (conftest shim R-35 ne root-cause fix kiya; ek green run evidence chahiye). timeout-minutes bhi 15→30 karna hoga |
| R-13 | `scripts/` junk drawer | TIER-1 DONE (31f3cbb — 23 grep-gated files → `scripts/attic/`); TIER-2 (~110 vps_*/.bat) = `docs/SCRIPTS_ATTIC_PLAN.md`, owner list-approval pe |
| R-14 | 7 misplaced test files | DONE (31f3cbb) — phase7_inline atticked; phase6/phase7/ws_test/key-probes KEPT (live refs — plan doc me detail) |
| R-15 | dead `app/config_production.py` | DONE (31f3cbb — atticked, zero imports verified) |
| R-16 | Stale-stack refs in active-ops docs | DONE (bcee216 — API.md Exotel→Vobiz, route-counts→1030, RB-003/007 strike-notes, Tara prompt Vobiz) |
| R-17 | Data-store registry | DONE (31f3cbb — `scripts/data_store_inventory.py` + `docs/DATA_STORES.md`: 209 stores, 20 PII-flagged) |
| R-18 | ruff non-gating | PARTIAL DONE (34e1322 — E9/F63/F7/F82 error-classes ab BLOCKING, clean verified; full-lint gate = baseline cleanup ke baad) |

## Phase 3 — feature completeness (safe items DONE 2026-07-05; UI items owner-input pe)

| ID | Gap | Status |
|---|---|---|
| R-19..R-21 | `leads.py`/`campaigns.py`/`niche_db.py` — UI ya deprecate | OPEN — decision ko VPS access-log data chahiye (`scripts/route_usage_audit.py --access-log`, ≥30 din) — is env se possible nahi; niche_db ke tests ab hain (R-29) |
| R-22..R-24 | `widgets.py` config tab / `conversion.py` builder / `booking.py` admin tab | OPEN — UI builds, alag scoped session (automation-control-center tab pattern) |
| R-25 | Customer webhook `payment.received`/`subscription.*` emits | OPEN — owner-set precondition kaayam: "wire after billing webhook handlers stabilize" (backlog 2026-06-16) |
| R-26 | LinkedIn scraper ToS tombstone | DONE (47f6f4f — scraping code REMOVED, surface preserved, kabhi implement nahi) |
| R-27 | Plivo/ARI stub tombstone docstrings | DONE (47f6f4f) |
| R-28 | Zoho duplicate integration | DONE (47f6f4f — hubspot.py ka copy DEAD tha (zero importers); zoho_crm.py canonical + shim) |
| R-29 | 5 untested dormant engines | DONE (9724ebe — 35 tests; niche_db 401/403 real-auth pinned) |

## USER-CONFIRM — owner decision pending

| ID | Gap | Status |
|---|---|---|
| R-06 | PII csv | PARTIAL DONE (46c1854 — HEAD se `git rm` + gitignore guard). **HISTORY me PII abhi bhi hai** — purge = `git filter-repo` + force-push + har clone/VPS re-clone coordinate; owner bole to alag operation |
| R-07 | Root `.xlsx` ×2 business files | USER-CONFIRM (untouched) |
| R-09 | `TASKS.md` | WONT-FIX (plan-then-build + retro skills reference karti hain) |
| R-34 | queue idempotency — 19 legacy tasks baseline me | RATCHET DONE (aee7b13 — NAYE gap pe hi CI red; baseline `scripts/queue_idempotency_baseline.json`). Legacy 19 ko idempotent banana = per-queue batches, alag sessions |

## CI-truth findings (PR #28 investigation, 2026-07-05)

| ID | Finding | Status |
|---|---|---|
| R-35 | Lock pair `httpx==0.28.1`+`starlette==0.35.1` tests ke liye incompatible — 16 files collection-error (main pe bhi) | DONE (48ab802 conftest shim; + ci.yml pehle se nahi, tests.yml/deploy-vps pin karte the). LONG-TERM: lock upgrade (fastapi/starlette pair bump) = alag decision |
| R-36 | mypy "MUST-PASS" step CI me kabhi REACH nahi hota tha; asli count = 1502 errors | ADVISORY kiya (34e1322) + 2 real bugs fix (fdfd2f1: dead KB warm-up main.py + festivals type-comment). Baseline cleanup ke baad wapas blocking |
| R-37 | `gap_analyzer._feature_detected` — hyphenated synonym keys `_normalise` se pass nahi hote → "Real-time notifications center" jaise features KABHI detected nahi = false-positive gaps admin backlog me | OPEN (R-29 tests ne pakda; fix = synonym keys ko bhi normalise karo — chhota, Phase 3 next batch) |
| R-38 | `niche_db.py` docstring auth-claim drift (bolti hai "sirf write ops pe admin", code 6/8 GETs pe bhi admin — code SAFER hai) | OPEN (docstring fix, trivial) |
| R-39 | **ci.yml `tests` job ~40 pre-existing voice/async failures** — R-35 collection-fix ne unmask kiye (pehle collection-crash pe 0 test chalte the). 2 causes: (a) ~30 "no event loop" = unpinned `pytest-asyncio` (lock ka purana reh jata); (b) ~10 "TelecallerBrain needs key" = voice tests bina key construct + `network`-unmarked | FIXED (ci.yml tests-job: tests.yml ki exact pin recipe `pytest==9.0.2 pytest-asyncio==1.3.0 httpx==0.27.2` + `GROQ_API_KEY: ci-dummy` env). Local verify: 51 previously-failing tests → all pass with pins+key. Full-suite re-run confirm pending |

## Phase 4 — deferred structural (EXPLICIT opt-in only)

| ID | Gap | Risk note | Status |
|---|---|---|---|
| R-30 | `main.py` 78 inline frontend routes → pages-router | route-ORDER change = first-route-wins landmine; snapshot-diff harness mandatory | PARKED |
| R-31 | 672 `os.getenv` → `settings` | getenv=live vs settings=boot-frozen — VPS flag-flip workflow risk | PARKED |
| R-32 | Godfile splits (vobiz_stream/telecaller_brain) | voice-unsafe per ADR | PARKED |
| R-33 | jsonl → Postgres (209 stores) | when-volume policy; R-17 registry DONE | PARKED |

---
*Seeded: 2026-07-05 (3-audit consolidation). Bulk execution: same-day "sab karo" (PR #28). Update protocol: status change = is file me edit + commit sha.*
