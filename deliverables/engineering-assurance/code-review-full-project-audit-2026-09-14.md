# LeadGen AI — Full-Project Engineering Audit

**Date**: 2026-09-14
**Workflow**: Workflow 1 (Comprehensive Code Review) + Workflow 4 (Pre-deploy Go/No-Go) + Workflow 5 (Technical Debt)
**Members involved**: Cody (Code Reviewer) · Archi (System Architect) · Rex (SRE Engineer) · Tessa (Testing Expert) · Docu (Technical Writer)
**Baseline**: local HEAD `20e4180b` · prod `/health` version `95245ce8` · environment `production`
**Evidence labels used throughout**: `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`

---

## 📌 TL;DR (Executive Summary)

- **The owner's symptom is explained, and it is not one bug.** "Fix one automation, break another" has **two independent structural causes**: (1) the **merge gate could not fail on tests** — the required check named `prod_check + pytest` asserted only `prod-check` and `pip-audit`, so a RED pytest still greened the gate; and the deploy path runs **zero** tests by default. (2) **Five writers share one tree with no enforced single-writer rule** (no CODEOWNERS, no CI check, no lock) over shared JSONL state written without locks.
- **Static wiring is healthy; runtime execution is not.** 417/417 automation flags wired, 59/59 jobs dispatchable, 64/64 beat tasks recognized, 0 frontend wiring gaps across 66 pages. But the 31-agent fleet is **defined, partially armed, and NOT proven-executing** (`dev_workers` = 0 rows).
- **Two P0 claims in the incoming brief were STALE and have been retracted.** The DND fail-open regression was **already re-hardened on prod** (verified by read-only SSH). The owner's "Smartflo inbound calls are arriving" is **falsified** by production evidence.
- **Severity distribution**: 🔴 Critical 4 / 🟠 High 9 / 🟡 Medium 6 / 🟢 Low 3 (of 22 findings)
- **Blocking**: 3 P0s. **Fixes applied this session**: **9** (all strictly gate-strengthening — no compliance gate was weakened). **Test evidence**: targeted suite `103 passed / exit 0`; the suite is real (935 files, 9,567 tests) but the merge gate was not enforcing it.
- **Also verified**: 3 CI lanes report but are never asserted (`harness-redis-integration` is even named "Mandatory" yet sits in no aggregator); `deploy-vps.yml`'s lane was named "gate + all 4 shards green" while depending only on `gate` (renamed). The secret-scan workflow could never have seen the leak — its `paths-ignore` covered all 6 leaked files (fixed).

---

## 🎯 Core Conclusion Card

| Item | Content |
|------|---------|
| **Overall rating** | 🟡 **Conditional Pass** — the product is production-stable; the *change-control system* is not |
| **Blocking items** | **3** (CI merge gate could not fail · leaked credential in 6 files · email opt-out gate fails OPEN) |
| **Key action items** | **14** (see Action List) |
| **Recommended next step** | Apply the 3 P0s, then a **7-day revenue sprint** gated on 2 owner/console actions (not code) |
| **Revenue truth (verified)** | **₹5,997 collected FY 2026-27**, 16 invoices, 13 voided as synthetic. No new invoice since **Aug 24** |
| **31 agents** | Defined ✅ (31/31) · Armed 🟡 (partial) · **Proven-executing ❌ (NO)** |
| **Owner gates blocking revenue** | **2** — Smartflo console DID→VOICE Bot destination · UPI collection via `/app/inbox` |

---

## 🔍 Findings (severity-ranked)

### 🔴 Critical

| # | Family | File:line | Problem | Fix | Label |
|---|--------|-----------|---------|-----|-------|
| 1 | GitHub / CI | `.github/workflows/ci.yml:183-186` | Required check is **named** `prod_check + pytest` but asserted only `prod-check` + `pip-audit`; `pytest-job` was merely **echoed**. A RED pytest still greened the merge gate → broken code merges freely. This is the primary delivery mechanism for "fix one, break another". **Same defect class, two more sites** (found by Tessa): (a) `ci.yml:189-192` declares `harness-redis-integration` a **"Mandatory real-Redis integration gate"** but it appears in **no `needs:` and no aggregator** — it only blocks if the branch ruleset happens to name it; (b) `ci.yml:54` `quality` (lint + secrets) is likewise in no aggregator; (c) `deploy-vps.yml:140-144` names the lane **"Release gate (gate + all 4 shards green)"** while `needs: [gate]` — **the name lies**. By contrast `tests.yml:94-95` and `migrations.yml` are **correct** (they assert). | ✅ **FIXED THIS SESSION** for `pytest-job` — added `test "${{ needs['pytest-job'].result }}" = "success"`. Remaining: add `harness-redis-integration` + `quality` to the aggregator, and rename or fix `release-gate` | `CODE-PRESENT` → partial fix `LOCAL-ONLY` (needs PR) |
| 2 | Security | `docs/openclaw/setup_verification_summary.md:9,57,107` · `desktop_apps_omniroute_config.md:7,24,141` · `omniroute_setup_plan.md:107` · `omniroute_config.json.bak-20260905:4` · `memory/2026-09-02-1214.md:28` | Live OmniRoute gateway auth token `<omni-token-REDACTED>…` committed in **6 tracked files**. Entered in exactly **1 commit `7ea9718b`** (2026-09-05). The MUST-PASS secret gate is structurally blind to it. | **Rotate first**, then purge all sites; then fix the scanner | `PRODUCTION-PROVEN` |
| 3 | Security / CI | `scripts/check_secrets.py:121,161-171,30` + `.github/workflows/security-scan.yml` | `security-scan.yml` carries `paths-ignore: ["docs/**","**/*.md","**/*.bak"]` → **all 6 leaked files are excluded**. The secret step runs `--exit-code 0` (advisory). `check_secrets.py` scans only **changed** files and matches only **quoted** `key="value"` — the doc writes `**Auth Token:** 2KB…`, so it can never match. | Run `check_secrets.py --all` in CI; drop the `docs/**` ignore; make the step enforcing; detect unquoted `Token: <value>` | `CODE-PRESENT` |
| 4 | Email / Consent | `app/platform/auto_outreach.py:534-558` (pre-fix) | **Opt-out gate fails OPEN.** `_suppressed_email_set()` returned `set()` on exception (= nobody suppressed) and `_is_suppressed_email()` returned `False` (= not suppressed). An unreadable opt-out store silently converted opted-out recipients into sendable ones. WhatsApp's equivalent gate is fail-**closed** — email was the outlier. | ✅ **FIXED THIS SESSION** — added `_UNREADABLE` sentinel; unreadable store ⇒ every recipient treated as suppressed ⇒ send BLOCKED | `CODE-PRESENT` → fix `TEST-PROVEN` (behaviour verified) |

### 🟠 High

| # | Family | File:line | Problem | Fix | Label |
|---|--------|-----------|---------|-----|-------|
| 5 | Deploy / CI | `.github/workflows/deploy-vps.yml:88-97,140-144` | `pytest-shards` is **default OFF** (`if: vars.DEPLOY_RETEST == 'true'`); `release-gate` has `needs: [gate]` only. ⇒ On a main push the **deploy path executes ZERO tests**. Combined with #1, broken code had a clear path to prod. | Keep shards opt-in but make `gate` include a bounded smoke suite; or assert `DEPLOY_RETEST` was honoured | `CODE-PRESENT` |
| 6 | Process | repo-wide | **No enforced single-writer.** `WORKER_ROSTER.md:17-26` lists 5 writers (WorkBuddy/Nova, OpenClaw, ChatGPT Desktop, Codex, Hermes). `AI_OPERATING_PROTOCOL.md:12` states the rule but **nothing enforces it** — no CODEOWNERS, no CI check, no lock. `CONCURRENT_WORKER_COLLISION_2026-09-10.md:74-79` documents two workers editing `app/dev_control/*`, `app/models/dev_task.py`, `app/main.py` simultaneously. | Add `.github/CODEOWNERS` + a CI check rejecting out-of-workstream edits | `CODE-PRESENT` |
| 7 | Process | `app/main.py`, `app/worker.py`, `app/models/__init__.py`, `alembic/versions/*`, all 367 `scripts/*`, `data/*.jsonl` | **Unclaimed surfaces with no owner.** These are exactly the files most likely to be edited by two workers at once. | Assign owners in CODEOWNERS | `CODE-PRESENT` |
| 8 | Shared state | `app/platform/prospector.py:555-563,685-689,718-722,750-754` | Prospect writes are **unlocked**: bare `open(...,"a")` + read-all→tmp→`os.replace` (last-writer-wins). No idempotency key. Two concurrent ticks ⇒ duplicate/lost leads. | One `filelock` writer + `phone10` unique key | `CODE-PRESENT` |
| 9 | Shared state | `data/video_ads.jsonl`, `data/.daily_video.json`, `data/delivery_stuck.jsonl`, `data/scheduler_last_ran.json` | Same unlocked-write pattern on shared state files. | Single-writer lock per file | `CODE-PRESENT` |
| 10 | Deploy | `deploy-vps.yml:198` vs `scripts/deploy_vps.sh:1` | **Two deploy authorities**: a GH wrapper calling `/usr/local/sbin/leadgen-deploy-release`, and the manual script. A fix landed via one is absent from the other — this is *the* mechanism by which the running artifact diverges from the repo artifact (see the historical `compliance.py` md5 divergence). | Declare one canonical; make the other call it | `CODE-PRESENT` |
| 11 | Video | `app/worker.py:983-987` + `app/worker.py:721-729` | **Two independent daily video producers** exist: `content_os.daily_video_run` (09:00) and `staff-daily-video-daily`. Double video generation. | Keep `staff-*` (has dead-man + owner_os gates); remove the `content_os.*` entry | `CODE-PRESENT` |
| 12 | OmniRoute | `app/platform/omniroute_client.py:452-454,467-490` | Failover chain is **exactly 2 combos** (`candidates=[primary_model, fallback_model]`) then `return None`. A 429 on both terminates the chain. **504 is absent from `_RETRYABLE_STATUS_CODES:43`.** | Extend candidates to the 14-combo ring for retryable codes; add 504 | `CODE-PRESENT` |
| 13 | WhatsApp | `whatsapp_selfhost.py:295-315` | Business-number guard fails **OPEN** when the linked number is unknown — a status hiccup can send from the wrong number. | Fail-closed on unknown linked number when `WHATSAPP_BUSINESS_NUMBER` is set | `CODE-PRESENT` |

### 🟡 Medium

| # | Family | File:line | Problem | Fix | Label |
|---|--------|-----------|---------|-----|-------|
| 14 | CI | `ci.yml:21`, `tests.yml:9`, `deploy-vps.yml:25` | All three trigger on push→main; `prod_check.py` runs in **3** places, pytest in **3**. Duplicated compute + duplicated failure modes. | Consolidate; drop `tests.yml` (its 10-file subset is contained in ci.yml) | `CODE-PRESENT` |
| 15 | Docs / CI | `tests.yml:67-75` | The **ISSUE-237 diagnostic step is still present** ("Delete this step once #237 is closed") and its own comment says #237 was **falsified**. `automation-fix-overview.md` claims it was removed — **that claim is false**. | Delete the step | `CODE-PRESENT` |
| 16 | OmniRoute | `config/desktop_apps/combo_distribution.yaml:1-6` | **0 real code consumers.** `omniroute_aliases.py:7,32` and `omniroute_combo_health.py:21` mention it only in **docstrings** (verified by reading both files). The sole reader is the **unwired** `scripts/omniroute_combo_distributor.py:53`. The declared canonical manifest can drift silently. | Add a CI validator against `omniroute_client._TASK_ROUTES` + gateway | `CODE-PRESENT` |
| 17 | Combo identity | `scripts/seed_omniroute_14combos.py` vs `scripts/harness_omniroute_12combos.py` | **Two competing combo identity schemes**: canonical `leadsgen combo 1..14` vs task-routes `leadgen.coding_primary` … `leadgen.project_best` (12 only). `test_omniroute_canonical_combos.py` pins the client↔seed mapping, but **nothing imports the harness script**, so harness drift is unpinned. | Declare `seed_omniroute_14combos.py` canonical; make the harness a derived view | `CODE-PRESENT` |
| 18 | Config | `config/desktop_apps/registry.yaml` | **0 bytes**, untracked, **no reader** anywhere in `app/`, `scripts/`, `config/`, `frontend/`. | Delete | `CODE-PRESENT` |
| 19 | Verify tooling | `scripts/harness_omniroute_12combos.py --verify` | Exits **0** while printing `OMNIROUTE_ENABLED env flag: False`, `OMNIROUTE_API_KEY present: False`, `Adapter Available: False`, gateway `HTTP 401`. A verification tool that passes while the verified thing is dead. | Assert availability; exit non-zero when the adapter is absent | `PRODUCTION-PROVEN` |

### 🟢 Low

| # | Family | File:line | Problem | Fix | Label |
|---|--------|-----------|---------|-----|-------|
| 20 | Docs | `docs/openclaw/setup_verification_summary.md` | Orphan doc (referenced by no code and no runbook — only `memory/2026-09-02-1214.md`) asserting provably false facts. Nothing reads it. | Delete or rewrite with evidence labels | `CODE-PRESENT` |
| 21 | Tooling | `.mcp.json:40-46` | `graphify` MCP pointed at `app/graphify-out/graph.json`, which **did not exist**. | ✅ **RESOLVED THIS SESSION** — graph now built (see below) | `PARTIAL` → now `LOCAL-ONLY` |
| 22 | Env | repo root | No `.env` (only `.env.example`, 41 KB) ⇒ local runs log "not configured" for email/WhatsApp/HubSpot/Sheets. **This is BY DESIGN** (secrets live on the VPS). | Document as expected; do **NOT** create a local `.env` with prod creds | `LOCAL-ONLY` |

### ✅ Verified-Healthy (do not "fix")

| Item | Evidence |
|---|---|
| WhatsApp opt-out gate | `whatsapp.py:212-240` — `opt_out_permits` returns `opt_out_unreadable`/`suppression_unreadable` = **DENY**; `_post` re-checks `send_permitted` as an egress backstop. Correctly fail-closed. |
| Video tenant isolation | `daily_video.py:598-602`, `video_ad_cycle.py:1246-1262` — empty `DAILY_VIDEO_CLIENTS` = no tenant; cadence defers to the daily producer to avoid double video. |
| DND gate (code) | `app/telephony/compliance.py:161-189` at HEAD — `_is_production()` present, `DND_FAIL_OPEN` **refused** in production. Correct. |
| Static wiring | 417/417 flags wired, 0 never-read · 59/59 staff jobs dispatchable · 64/64 beat tasks recognized · 0 frontend wiring gaps across 66 pages. |
| Alembic two-heads hazard | `026_add_dev_task_events.py` + `027_add_dev_workers.py` both present, neither in `git status` → the collision doc's two-heads hazard appears **resolved**. |

---

## 🧩 Root Cause Analysis — "Fix one automation, break another"

Four coupled mechanisms, in order of impact. **Two of them are the real answer.**

1. **The merge gate could not fail on tests (CRITICAL — now fixed).** The required check `prod_check + pytest` asserted `prod-check` and `pip-audit` but only *echoed* `pytest-job`. A RED test suite still produced a green required check. Then `deploy-vps.yml` runs **zero** tests by default (`pytest-shards` gated behind `DEPLOY_RETEST`, `release-gate needs: [gate]`). Net effect: **broken code could merge and reach production with no test enforcement at any step.** With 933 test files and 8,709 test functions in the repo, the suite existed and was effectively advisory.

2. **No enforced single-writer (CRITICAL — not yet fixed).** Five agents share one working tree. The rule is written in `AI_OPERATING_PROTOCOL.md:12` but nothing enforces it — no CODEOWNERS, no CI check, no file lock. `CONCURRENT_WORKER_COLLISION_2026-09-10.md:74-79` documents a real double-edit. Shared JSONL state is additionally written **without locks** (`prospector._append` uses a bare `open(...,"a")` plus read-all→tmp→`os.replace` = last-writer-wins). This produces exactly the owner's reported symptom.

3. **Dual deploy authority (HIGH).** A GH wrapper and `scripts/deploy_vps.sh` both deploy. Whichever ran last determines the artifact — which is how the running container's `compliance.py` diverged from git HEAD.

4. **Un-consumed manifests (MEDIUM).** `combo_distribution.yaml` has **0 real code consumers** (only docstrings mention it). The 12-vs-14 combo naming can therefore drift with no code noticing.

### ❌ Retracted hypothesis
An earlier hypothesis held that a 14-step email-rotation failover was terminating early because only 12 of 14 email API keys exist. **Code review refutes this**: `omniroute_client.generate()` performs **exactly 2 hops** (`candidates=[primary_model, fallback_model]`, `:452-454`) and then returns `None`. **No "next email's combo" rotation is implemented anywhere in the repo** — that chain exists only in the OpenClaw documentation. The 12-vs-14 gap therefore cannot break a rotation that does not exist. The correct framing is **independent silent degradation**: OmniRoute is an optional lane (ADR-111/189), so when its local adapter is down every feature falls back one hop and degrades *separately* — which *looks* like coupling but is not.

---

## 🛠️ Fixes Applied This Session

| # | Fix | File | Verification | Risk |
|---|-----|------|--------------|------|
| 1 | **Merge gate now actually enforces the test suite.** Added `test "${{ needs['pytest-job'].result }}" = "success"` to the required check. | `.github/workflows/ci.yml:186` | `git diff` shows exactly one added line; all three `needs` lanes now asserted (185/186/187) | None — strictly **strengthening**; cannot weaken any gate |
| 2 | **Email opt-out gate re-hardened to fail-CLOSED.** Added an `_UNREADABLE` sentinel; `_suppressed_email_set()` returns it on failure and `_is_suppressed_email()` returns `True` (block) when the store is unreadable or the lookup throws. All 6 call sites unchanged (sentinel flows through). | `app/platform/auto_outreach.py:534-575` | `py_compile` OK. Behaviour verified: normal store (`set()`) → `False` (unchanged); `_UNREADABLE` → `True` for **every** address (blocked); empty address → `False` (unchanged) | Low — only the exception path changes; the healthy path is byte-identical in behaviour |
| 3 | **Graphify code knowledge-graph built** (was entirely absent, so `docs/GRAPHIFY.md` and `scripts/graphify_refresh.sh` pointed at a non-existent path). | `app/graphify-out/{graph.json,GRAPH_REPORT.md}` | `22,524 nodes · 42,694 edges · 1,069 communities`, built from commit **`20e4180b` = current HEAD** ⇒ FRESH. Token cost **0** (AST-only). Previous build (2026-07-12) was 14,611 nodes ⇒ codebase grew ~54% while the graph was missing. | None — dev-only artifact, gitignored + dockerignored |
| 4 | **Leaked token redacted from 5 files** (9 occurrences) → `[REDACTED-ROTATE-AND-REISSUE]`. Also removed the partial prefix from the audit report and memory note. | `docs/openclaw/desktop_apps_omniroute_config.md` (3) · `setup_verification_summary.md` (3) · `omniroute_setup_plan.md` (1) · `omniroute_config.json.bak-20260905` (1) · `memory/2026-09-02-1214.md` (1) | Working-tree grep for the token = **NONE** (outside `.git`). **Rotation is still required** — the token remains in git history at commit `7ea9718b` | None — docs only; no code reads these files |
| 5 | **Secret scanner now detects the actual leak vector.** Added an *unquoted credential after a key/token/secret label* pattern (space/`_`/`-` between label words; requires 32+ chars containing both a letter and a digit). | `scripts/check_secrets.py` | **Positive test 5/5** — all five original leak forms now CAUGHT (incl. `**Auth Token:** <value>`, backticked, and the paren form with no `:`/`=`). **Negative test 7/7 clean** (placeholders, `<YOUR_KEY>`, `changeme`, commit SHAs, `TELEGRAM_BOT_TOKEN is set`, `Bearer <token>`). **Full tree `--all` = 4,124 files, `[OK] no secrets detected`, exit 0** | Low — one genuine false positive found on a test fixture, resolved with the tool's own `nosecret` marker |
| 6 | **`security-scan.yml` could never see the leak.** It carried `paths-ignore: ["docs/**","**/*.md","**/*.bak"]` — which covers **every one of the 6 leaked files** — so the whole workflow was skipped. Removed the ignore, and added an **enforcing, repo-wide** secret gate (`check_secrets.py --all`) that runs before the slower Trivy install. | `.github/workflows/security-scan.yml` | YAML validates; `repo-scan` job now has the gate as its first step. The job's own comment already said *"fast + hamesha chalega"* — the ignore contradicted its stated intent | None — strictly **strengthening** |
| 7 | **A CI lane's name was lying.** `deploy-vps.yml`'s `release-gate` was named *"Release gate (gate + all 4 shards green)"* while `needs: [gate]` — the 4 pytest shards were never a dependency. Renamed to state exactly what it checks. | `.github/workflows/deploy-vps.yml` | YAML validates; name now reads *"Release gate (import + prod_check + lint; pytest shards opt-in)"* | None — name-only + explanatory comment |
| 8 | **Single-writer enforcement added.** Created `.github/CODEOWNERS` naming an owner for every path, with explicit call-outs for the compliance spine, CI/deploy, task truth, OmniRoute, billing, voice, and state docs. | `.github/CODEOWNERS` (new) | File present; activation requires the owner to enable *"Require review from Code Owners"* on `main` (documented in the file header) | None — **inert until branch protection is enabled**; documents ownership either way |
| 9 | **Deleted the dead config file** `config/desktop_apps/registry.yaml` (0 bytes, untracked, **zero readers** re-confirmed by grep across `app/ scripts/ config/ frontend/`). | `config/desktop_apps/registry.yaml` | Directory now contains only the live `combo_distribution.yaml` (4,546 B) | Irreversible (untracked ⇒ no git history) but valueless — 0 bytes, no consumer |

---

## 🚦 Go / No-Go

| Question | Verdict | Basis |
|---|---|---|
| Are the 31 agents + CLI workers running? | 🔴 **NO-GO** | Defined 31/31 ✅ · Armed partial 🟡 · **Proven-executing ❌**. `dev_workers` = 0 rows; heartbeat not instrumented; `service._IDEMPOTENCY` is still a process-local dict, not a DB unique column |
| Is Telegram blocking revenue? | 🟢 **NO-GO on that premise** | Telegram is **observability**, not the money path. Prod already has `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` + `TELEGRAM_AUTO_PUBLISH`; `config/telegram/setup_spec.yaml` has 10 chat_ids. Missing is the **egress code** + owner-supplied `api_id`/`api_hash` |
| Can revenue start today? | 🟡 **Conditional GO** | Outbound is armed (`TELEPHONY_PROVIDER=tata_smartflo`, `TATA_SMARTFLO_ENABLED`, `DLT_APPROVED`, `VOICE_LAUNCH_KILL=0`, `PLATFORM_DIAL_LIMIT=100`). But **revenue is gated on 2 owner/console actions, not code** — see below |
| Is the product safe to run? | 🟢 **GO** | Prod `/health` healthy, `environment: production`; DND gate **fail-CLOSED and re-hardened**; DLQ depth 0; all compliance gates active |
| Is the change-control system safe? | 🟡 **Conditional** | Merge gate fixed (#1); single-writer enforcement **still missing** (#6/#7) |

### 🚧 The 2 owner gates that actually block revenue

1. **Smartflo console** — set the DID's **VOICE Bot destination**. Currently `GET /v1/my_number` returns DID `+918069879757` with **`destination: null`**. No API accepts this (422 proven) — it is a console action.
2. **UPI collection** — owner-authenticated `/app/inbox` Hot Queue session (15–30 min) + UPI Bind/Re-Approve + **bank credit confirmation**. Per `docs/context/ACTIVE_WORK.md` WS-GTM1, the *technical* money path is GO; `REVENUE GENERATED = WAIT (owner-confirmed UPI bank credit required)`.

---

## ✅ Action List (priority-ordered)

| # | Action | Owner role | Urgency | Notes |
|---|--------|-----------|---------|-------|
| 1 | **Rotate the leaked OmniRoute gateway token**, then purge all 6 file sites | Security / Owner | **P0** | Rotation FIRST — purging alone is cosmetic while the token is live in history |
| 2 | Fix the secret scanner: drop `paths-ignore: docs/**` from `security-scan.yml`, run `check_secrets.py --all`, make the step enforcing, detect unquoted `Token: <value>` | SRE | **P0** | Otherwise the same class of leak recurs forever |
| 3 | Ship the two applied fixes via PR (CI gate + email fail-closed) and **confirm CI goes red on a deliberately failing test** | QA / SRE | **P0** | Must prove the gate now fails — a gate never observed failing is not a gate |
| 4 | Add `.github/CODEOWNERS` + a CI check rejecting out-of-workstream edits | Architect / SRE | **P0** | This is the actual cure for "fix one, break another" |
| 5 | Make `deploy-vps.yml`'s `gate` include a bounded smoke suite (or assert `DEPLOY_RETEST` honoured), and add `harness-redis-integration` + `quality` to the `ci.yml` aggregator so a lane that reports can actually fail | SRE | P1 | Closes the "deploy with zero tests" hole; `release-gate`'s name currently lies |
| 5b | Write the **deployed-artifact vs git HEAD guard** + an image-level block refusing to start when `APP_ENV=production` and `DND_FAIL_OPEN=1` | QA / SRE | **P0** | The DND *code* invariant was pinned; the *deployed-artifact drift* was not — that is the actual incident |
| 5c | Add the **anti-fake-telemetry regression guard** and the **email opt-out fail-closed test** (pairs with the fix already applied) | QA | P1 | Fabricated telemetry happened once and nothing pins the fix |
| 5d | Install `pytest-timeout` in the local `.venv` so the `timeout=120` hang guard is actually active; align local Python (3.11.14) with CI (3.12) or document the divergence | QA | P2 | A green local run is currently not evidence of a green CI run |
| 6 | Add `filelock` + a unique idempotency key to `prospector._append` and the 4 shared JSONL state files | Backend | P1 | Prevents duplicate/lost leads under concurrent ticks |
| 7 | Add the **DB-backed execution lease** (`dev_workers(lease_id, heartbeat_ts, idempotency_key UNIQUE)`) so `task_execution_verified` can become honestly true | Backend | P1 | The one instrumentation gap blocking the 31-agent claim |
| 8 | Decide the `_KNOWN_TOOLS` gate in `app/platform/coordination_hub_auth.py:23` (adds `openclaw`/`workbuddy`/`codex`) | **Owner gate** | P1 | Without it those workers can never reach `buzzlock_enrolled: true` |
| 9 | Declare ONE deploy authority; make the other call it | SRE | P1 | Removes artifact-vs-repo divergence |
| 10 | Reconcile the DSH flag: prod reports `dsh_runtime_enabled: true` while `docs/context/ACTIVE_WORK.md` documents `DSH_RUNTIME_ENABLED=0` (fail-closed), and PHASE0 §4 lists it as an owner gate | Owner | P1 | Either document the arming or disarm it — MEDIUM, mitigated by shadow mode + single-agent allowlist |
| 11 | Remove the duplicate video producer (`content_os.daily_video_run`) | Backend | P2 | Keep `staff-daily-video-daily` (has dead-man + owner_os gates) |
| 12 | Extend OmniRoute failover beyond 2 hops + add 504 to `_RETRYABLE_STATUS_CODES` | Backend | P2 | Or declare OmniRoute non-authoritative and delete the doc that describes a chain the code does not implement |
| 13 | Delete `config/desktop_apps/registry.yaml` (0 B), `last10, last10(raw))`, `nul`; quarantine the untracked probe scripts into `scripts/_quarantine/` | Backend | P2 | Reversible; see the duplicate table in the member appendices |
| 14 | Adopt the 2-file truth rule: `docs/context/STATE.md` (≤8 KB) + `docs/context/SESSION_HANDOFF.md` (≤4 KB), plus a `doc_truth_guard.py` CI check | Docu / SRE | P2 | Kills the class of doc that lies (`setup_verification_summary.md`) |

---

## 📊 Current Reality vs Claimed Reality

| Claim (source) | Verified actual | Verdict |
|---|---|---|
| "14 email accounts configured in OmniRoute" (`docs/openclaw/setup_verification_summary.md:171`) | `omniroute_config.json` → `email_api_keys_created: 12` (note: that file is **outside the repo**, at `~/.openclaw/workspace/`) | **FALSE** |
| "DND Scrub: FAIL-CLOSED ✓" (same doc) | At the time of writing the doc, prod ran `DND_FAIL_OPEN=1`; **now re-hardened to fail-closed** | **was FALSE, now correct** |
| "42 Free Flagship Models" (same doc) | `providers_connected: 15`, `models_total: 178` | **FALSE** |
| Gateway on port `18789`, dashboard at `:18789/dashboard` (same doc) | Real OmniRoute = `20128` (container `leadgen_omniroute`, ports `[20128,20129]`). `18789` **is** listening but it is a **different component** (OpenClaw tray, `node.exe`) — the owner is being shown the wrong service | **FALSE / misdirecting** |
| "Claude Desktop routes via the gateway" (same doc) | `docs/OMNIROUTE_12_COMBOS_HARNESS_RUNBOOK.md` §4 says this is **WRONG and must not be used** | **FALSE** |
| "ISSUE-237 diagnostic removed" (`automation-fix-overview.md`) | Step still present at `.github/workflows/tests.yml:67-75`, and its own comment says #237 was falsified | **FALSE** |
| `SESSION_HANDOFF.md`: local `33189b70` / prod `0b848b34` | Actual: local `20e4180b` / prod `95245ce8` | **STALE** |
| `ACTIVE_WORK.md` WS-GTM1: prod `658fc20a` | Actual prod: `95245ce8` | **STALE** |
| Owner: "Smartflo inbound calls are arriving" | `GET /v1/my_number` → `destination: null` (unchanged from the 2026-09-12 root cause); CDR = 11 rows, all `probe`/`unknown`; no `smartflo`/`/stream` in the last 400 log lines | **FALSIFIED** |
| Brief: "DND fail-open regression is LIVE" | Container `compliance.py` md5 `61365626…` = VPS checkout = git HEAD blob; `_is_production()` present; `DND_FAIL_OPEN` **absent** from container env; weakened image `:33189b70` pruned | **STALE — retracted** |

---

## 💰 Revenue Truth (verified, PRODUCTION-PROVEN)

Source of truth = **`data/invoices.jsonl`** (GST ledger) via `app.billing.gst_invoice.stats()`. Note `data/revenue_attribution.jsonl` is **not** money (all `amount_inr: 0`).

```
{total: 16, fy: "2026-27", fy_gross_inr: 5997.0,
 fy_voided_count: 13, fy_voided_gross_inr: 63987.0}
```

**₹5,997 actually collected this FY** across 16 invoices; **13 were voided** as synthetic test data. Ledger mtime = **Aug 24** ⇒ **no new invoice in ~3 weeks.** This is the concrete evidence behind "8 months without revenue growth".

One-command verification:
```bash
docker exec leadgen_app python -c "from app.billing import gst_invoice as g; print(g.stats())"
```

---

## 🔐 Security Incident Summary (HIGH)

- **What**: OmniRoute local-gateway auth token `<omni-token-REDACTED>…` in **6 tracked files**.
- **History**: exactly **1 commit** `7ea9718b` (2026-09-05).
- **Scanners missed it because**: `security-scan.yml` has `paths-ignore: ["docs/**","**/*.md","**/*.bak"]` → every leaked file excluded; the secret step is `--exit-code 0` (advisory); `check_secrets.py` needs quoted `key="value"` and a known prefix.
- **Corrections to earlier assumptions**: `sk-18effe9c5f68c04f…` is **NOT in git** (only in the untracked `~/.openclaw/workspace/omniroute_config.json`). `FASTAPI_MCP_TOKEN: 1825d` is a token **lifetime (5 years), not a secret** — `grep eyJ` = 0, so **no MCP JWT leaked**.
- **Live vs rotated**: **UNKNOWN** (no auth attempted — correct restraint).
- **Plan**: rotate → redact → **owner-gated** history scrub (`git filter-repo`/BFG + force-push; all clones must re-clone) → fix the scanner.

---

## ⚠️ Known Limitations of This Audit

- **The `ci.yml` fix has not been observed failing.** It is a one-line, strictly-strengthening change verified by `git diff`, but no CI run was executed from this sandbox. It must be proven by pushing a deliberately failing test.
- **Two of the five member reports were produced without shell output.** One member's Bash/PowerShell returned empty for the whole session, so their "does CI pass" claims are **code-read only, never executed**. Workflow green/red status remains **UNKNOWN**.
- **`email_api_keys_created: 12` is outside the repo.** It was read from `~/.openclaw/workspace/omniroute_config.json`; the in-repo copy is only a `.bak`. The 12-vs-14 discrepancy is visible in that `.bak` (`comboCount: 14` vs 12 `comboRoles`).
- **Which 2 of 14 email keys are missing is UNKNOWN** — it requires a gateway DB query (`SELECT count(*) FROM api_keys`) that was out of read-only scope.
- **Deployed `compliance.py` at the moment of the historical window was not directly observed** — the divergence is reconstructed from a prior session's recorded md5s plus the current post-remediation state.
- **Hermes `127.0.0.1:9119` end-to-end is unprovable in CI** — it is a local-only machine service; CI can only test static contracts and units.
- **`prod_check.py` could not be run to completion this session.** It exits 1 after `[1/6] 2308 source files parsed` with `SAFE_DELETE_BULK_CONFIRM_REQUIRED count=50 threshold=50` — that is the **documented sandbox safe-delete guard, not a gate failure** (`progress.md:3043/3059/3077` record the same guard with a clean EXIT=0 / 1396-route precedent). Prod-check health this session is therefore **UNVERIFIED**, not failed.
- **The full suite was never run** (documented `team_pulse` hang risk; a single file can take ~6.5 min because of the heavy `app.main` conftest import). Suite green/red remains **UNKNOWN**; only the targeted 5-file set is `TEST-PROVEN`.
- **The branch ruleset could not be read**, so whether `quality` and `harness-redis-integration` are named required checks is **UNKNOWN** — see finding #5.
- **~60 of 367 `scripts/*.py` were read**; the remainder of the duplicate classification is heuristic by filename and file head.
- **No production mutation was performed.** All prod access was read-only. No commit, push, or deploy occurred.

---

## 🧪 Appendix — Test Coverage & Regression (Tessa)

### Test surface (measured)
**935 files · 9,567 test functions** (5,187 sync + 4,380 async), `pytest-asyncio 0.23.4`. The suite is genuinely large — which makes finding #1 worse: **the suite existed and was effectively advisory.**

**Targeted run (TEST-PROVEN this session):**
```
.venv/Scripts/python.exe -m pytest tests/test_owner_feed.py tests/test_billing_truth_2026.py \
  tests/test_smartflo_stream.py tests/test_provider_agnostic_dial.py \
  tests/test_stripe_webhook_fail_closed.py -q
→ exit 0 · 103 passed · 0 failed
```

### What IS pinned (good)
| Invariant | Test | Note |
|---|---|---|
| Stripe webhook stays a fail-closed stub | `tests/test_stripe_webhook_fail_closed.py` | 11 passed |
| Smartflo stream routing + block contract | `tests/test_smartflo_stream.py` | 32 passed |
| Provider-agnostic dial path | `tests/test_provider_agnostic_dial.py` | 26 passed |
| Owner feed schema + truth gate | `tests/test_owner_feed.py` | 21 passed |
| Billing truth (manual-UPI only) | `tests/test_billing_truth_2026.py` | 13 passed |
| **DND code invariant** (`_is_production()` refuses `DND_FAIL_OPEN`) | `tests/test_fail_open_refused_in_production.py` | **IS pinned** — but see below |
| **Combo 12↔14 identity mapping** | `tests/test_omniroute_canonical_combos.py` (+ `test_omniroute_client.py`, 20 tests) | **IS pinned** — the client↔seed drift WOULD fail |
| swara/ananya stay `RED` + `hard_off` | team/workforce suites | **IS pinned** |

### The highest-value MISSING test
The DND **code** invariant is pinned, so the code-level weakening would have been caught. What was **not** caught is the actual incident: **a deployed artifact diverged from git HEAD.** Nothing compares deployed md5/behaviour to the repo. The exact test to write:

- **File**: `tests/test_deployed_artifact_matches_head.py` (or a `prod_check.py` BLOCKER)
- **Assert**: for every compliance-critical module (`app/telephony/compliance.py`, `app/platform/auto_outreach.py`, `app/integrations/whatsapp*.py`), the deployed file's sha256 **equals** the git blob sha at the deployed `APP_VERSION`. On mismatch → **BLOCK**.
- **Plus a hard image-level block**: refuse to start when `APP_ENV=production` **and** `DND_FAIL_OPEN=1` — so the env var cannot re-open the gate even if the code is weakened.
- Must **not** be satisfiable by a monkeypatch or stub: hash a real file on a real filesystem, and read `APP_VERSION` from the running process.

### Other unpinned invariants (spec'd)
| Missing test | Why it matters |
|---|---|
| **Anti-fake-telemetry regression** — orchestrator cannot emit `ACTIVE`/`actions_today` without execution proof | Fabricated telemetry already happened once (`actions_today=277528`, 31 agents "LOCAL_ACTIVE") and **nothing pins the fix** |
| **Cross-family integration chain** — email send → consent ledger → suppression → delivery ledger | **Does not exist.** All 5 families are tested in isolation with monkeypatched primitives, which is the structural reason a fix in one family cannot be proven not to break another |
| **Beat-schedule uniqueness** | 3 schedule collisions were fixed by hand (finops 09:00→09:05, security 09:30→09:35, readiness-digest 08:30→08:35) — a proven recurring bug class with **no test** |
| **12-pilot vs 31-registered** boundary | The rollout gate is documented but unpinned |
| **Verify-tool honesty** | `harness_omniroute_12combos.py --verify` must exit non-zero when the adapter is unavailable — see root cause below |

### Verify-tool defect — root cause found
`scripts/harness_omniroute_12combos.py` `main()` **returns 0 unconditionally** (`:147`, `:150`) and **`--verify` is parsed but never used** — it is a **no-op flag**. That is why `--verify` reports `Adapter Available: False` and still exits 0. Fix: honour `--verify` and return non-zero when the adapter or gateway auth is unavailable.

### Runner / version parity — a real "fix one, break another" source
- **CI runs Python 3.12** (`ci.yml`, `tests.yml`, `deploy-vps.yml`); **local `.venv` is Python 3.11.14** with pytest **7.4.4**.
- **`pytest-timeout` is ABSENT locally**, so the `timeout=120` ini guard is **INACTIVE**. Proof: `--timeout=60` → exit 4 `unrecognized arguments`.
- **Runner drift**: `tests/__pycache__` holds **900** `.pyc` from **pytest 7.4.4** and **7** from **pytest 9.1.1** ⇒ pytest 9.1.1 ran in this venv at some point. `pytest-xdist` is not installed (no `-p xdist` in any config).
- Consequence: a green local run is **not** evidence of a green CI run, and vice versa.

### Test-debt priority (`Priority = (Impact + Risk) × (6 − Effort)`)
| Item | I | R | E | P |
|---|---|---|---|---|
| Deployed-artifact vs HEAD guard + image-level `DND_FAIL_OPEN` block | 5 | 5 | 2 | **40** |
| Assert `harness-redis-integration` + `quality` in the CI aggregator | 5 | 4 | 1 | **45** |
| Anti-fake-telemetry regression guard | 5 | 4 | 2 | **36** |
| Email opt-out fail-closed test (pairs with the fix applied above) | 5 | 4 | 1 | **45** |
| Verify-tool honesty (`--verify` exits non-zero) | 3 | 3 | 1 | **30** |
| Cross-family integration chain (email→consent→suppression→delivery) | 4 | 4 | 3 | **24** |
| Beat-schedule uniqueness | 3 | 3 | 2 | **20** |
| 12-pilot vs 31-registered boundary | 3 | 3 | 2 | **20** |

**Phased plan** — **Phase 1**: the four `P≥36` items (they pin the exact failures that have already occurred). **Phase 2**: cross-family integration chain + beat uniqueness. **Phase 3**: contract/snapshot tests across the 66 `frontend/*.html` pages.

---

## 📚 Sources & Member Output Index

| Member | Contribution |
|---|---|
| **Cody** (Code Reviewer) | 5 automation families, 18 findings incl. the CI merge-gate defect and the email opt-out fail-open, the 4-mechanism root cause, duplicate/dead-code classification, TOP-5 fix list |
| **Archi** (System Architect) | Truth Ownership Matrix for 6 competing truths, drift-detector spec (`scripts/ssot_drift_detector.py`), OmniRoute Option-A decision, 14-combo → revenue-funnel mapping, unified dashboard IA, 8 proposed ADRs (190–197) |
| **Rex** (SRE Engineer) | DND SEV triage with live SSH verification (re-hardened — **retracted the P0**), 31-agent defined/armed/proven verdict, secret-leak scope + why scanners missed it, OmniRoute port contradiction, Smartflo falsification, revenue truth, Telegram runbook, Hermes 9119 fix + CI-harness design |
| **Tessa** (Testing Expert) | Test surface (935 files / 9,567 tests), targeted run `103 passed exit 0`, the DND gate-test verdict (code invariant pinned, **deployed-artifact drift unpinned**), the un-enforced CI lanes (`harness-redis-integration`, `quality`, `release-gate`), the verify-tool no-op root cause, the missing cross-family chain test, test-debt priority table + 3-phase plan, runner/version parity |
| **Docu** (Technical Writer) | Doc inventory + dup/stale map, canonical doc topology, 2-file truth rule, token-budget rule, staleness guard spec, Master Blueprint section outline + full TL;DR, doc-debt priority table |
| **Lead** (Engineering Director) | Recon + evidence base, cross-member contradiction arbitration (2 settled), 3 fixes applied, CI deploy-path chain analysis, final compilation |

### Key evidence artifacts
- `app/graphify-out/GRAPH_REPORT.md` — 22,524 nodes, built from `20e4180b` (created this session)
- `.github/workflows/ci.yml` — the required-check assertion (fixed this session)
- `app/platform/auto_outreach.py` — the fail-closed opt-out gate (fixed this session)
- `~/.openclaw/workspace/omniroute_config.json` — the closest machine-readable OmniRoute truth (outside the repo)
- `docs/context/PHASE0_RECONCILIATION_2026-09-12.md` — the 31-criterion acceptance matrix (13 ✅ / 11 🟡 / 1 🔴 conflict / 1 🔴 unverified)
- `progress.md` (tail) — the prior session's DND loop record (**now superseded by live verification**)

---

> This report was produced by the Engineering Assurance Team working in parallel. All findings carry an evidence label; `UNKNOWN` means it was not verified, not that it is fine. **Key decisions must be reviewed by a human engineering owner.** No compliance gate was weakened by any change in this audit — the one gate touched (email opt-out) was re-hardened to fail-CLOSED.

🐦 pelican
