# Autonomous Admin — Execution Ledger (2026-09-18)

> Owner-mandated, evidence-based execution record. Every claim below is backed by a
> command whose output was observed live. Unverified items are labelled `CODE-PRESENT`,
> `PARTIAL`, `BLOCKED` or `NOT CHECKED` — never "working".

**Truth priority applied:** LIVE RUNTIME EVIDENCE → CURRENT CODE → CURRENT TESTS →
CURRENT CONFIGURATION → CURRENT DOCS → OLD REPORTS.

---

## 1. PRODUCTION BASELINE (live, 2026-09-18 ~13:15–13:25 IST)

| Item | Live value | Evidence |
| --- | --- | --- |
| Repo | `C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent` | local |
| `origin/main` | `c4547ab1` (2026-09-17T17:58:13+05:30) | `git rev-parse origin/main` |
| Working branch | `fix/runtime-data-baseline-cline-0918` | `git status -sb` |
| **Live prod `/health`** | `version=680722c8`, `environment=production` | `GET https://leadsgenai.in/health` |
| Prod git HEAD | `680722c8` (ancestor of `origin/main`) | `ssh root@leadsgenai.in 'git rev-parse HEAD'` |
| Prod image | `ghcr.io/sumitrevolt/leadgenrationaivoiceagent:680722c8` | `docker ps` |
| Prod containers | `leadgen_app` (127.0.0.1:8000), `leadgen_mcp` (127.0.0.1:8090), `leadgen_worker`, `leadgen_scheduler`, `leadgen_worker_video`, `leadgen_worker_heavy`, `leadgen_redis` — all `healthy` | `docker ps` |
| Prod disk | `/dev/sda1 193G, 99G used, 94G free (52%)` | `df -h /` |
| Prod RAM | `15992 MB total, 6940 used, 9051 available` | `free -m` |
| `leadgen-omni-bridge.service` | **active running** | `systemctl` |
| `leadgen-call-loop.service` | **inactive dead** ⚠️ | `systemctl` |
| `leadgen-calls.service` | **inactive dead** ⚠️ | `systemctl` |
| GitHub auth | `sumitrevolt` (gist, read:org, repo, workflow) | `gh auth status` |
| TypeSafe live probe (prior) | `POST /v1/systemone` → 200, model `jev-1.13.0`, 1.04s | `docs/ADMIN_EXECUTION_WAVE1_20260918.md` |

**Doc drift corrected:** `CLAUDE.md` §Ops-facts still records prod `/health` as `cdc28e0d`
(and `95245ce8`, `0b848b34` before that). Live truth is **`680722c8`**. Any SHA claim must be
re-probed, not read from docs.

---

## 2. P0 FINDINGS — FOUND AND FIXED THIS SESSION

### P0-1 — Cold-email acquisition engine was 0 bytes in production 🔴

**The highest-impact defect found.** Commit `cf48e33f`
("feat: crore-strategy foundation — M1-M5 stubs + wiring + tests (5,218 lines)",
2026-09-17T06:14:05+05:30) deleted **1,982 lines** from
`app/platform/auto_outreach.py`, leaving a **0-byte file**.

* Git blob in `origin/main` and `HEAD`: `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`
  (the well-known *empty blob* SHA).
* **Live production proof:**
  `ssh root@leadsgenai.in 'ls -l /opt/leadgen/app/platform/auto_outreach.py'` →
  `-rw-r--r-- 1 root root 0 Sep 17 01:33 /opt/leadgen/app/platform/auto_outreach.py`
* `emptying_commit_in_prod = True` (`git merge-base --is-ancestor cf48e33f 680722c8`).

**Blast radius (every call raised `AttributeError`):** 19 call sites in
`app/api/team.py`, plus `app/agents/staff.py:1127` (the cold-email staff job),
`app/api/admin_dashboard_builders.py:695`, `app/api/admin.py:674`.
Functions lost: `run_email_outreach`, `run_email_followups`, `outreach_stats`,
`outreach_activity`, `last_run_summaries`, `pending_review_candidates`,
`record_review_decision`, `list_review_decisions`, `review_decision_counts`.

Cold email is the documented top of the revenue funnel (`/audit` → email-outreach →
inquiry → `/pricing` → `/start`), so this was a **revenue-channel outage**, not dead code.

**Fix:** restored the last-good blob verbatim — `3f697883effdf03aa7d8d5674c79a6ee24f9eb27`
(identical at `cf48e33f^` and `f5ef19bf`). Commit `344cb5e5`, +1,982 lines.
**Rollback:** `git checkout e69de29b -- app/platform/auto_outreach.py`.

### P0-2 — Two writers, two formats, one path: task-ledger data loss 🔴

`app/platform/dev_workers.py` declared
`LEDGER_PATH = data/orchestrator_ledger.db` — the *same* path
`automation_orchestrator.SQLITE_DB_PATH` (`DurableTaskStore`) and `DevWorkerStore`
open as **SQLite**. But `DevWorkerProver._save()` writes **JSON** via
`open(path, "w")` + `json.dump`.

Live evidence — the file's first bytes were
`7B 0D 0A 20 20 22 64 65 76 5F 77 6F 72 6B 65 72` → `{ "dev_worker`, i.e. JSON,
not `SQLite format 3`.

**Fix:** the prover now owns `data/dev_workers_ledger.json`; `get_prover()` resolves
the path at call time so `DEV_WORKERS_LEDGER_PATH` can redirect it. Commit `7bb050d4`.

### P0-3 — CI `prod_check runtime gates` blocked on 3 real problems 🟠

PR #522's CI failed with exactly:

```
[FAIL] 3 problem(s):
  - SYNTAX tests/test_dev_workers.py line 1: invalid non-printable character U+FEFF
  - AUTOMATION DEAD FLAG: OUTREACH_CAMPAIGN_VARIANTS declared in AUTOMATION_FLAGS but never read in app/
  - AUTOMATION DEAD FLAG: OUTREACH_AUDIT_LED declared in AUTOMATION_FLAGS but never read in app/
```

1. **UTF-8 BOM** (`EF BB BF`) on line 1 of `tests/test_dev_workers.py` — the only BOM in the
   entire tracked `*.py` set. It was a hard syntax error, and it meant pytest never collected
   the file at all. BOM stripped; double-encoded em-dash on line 1 repaired.
2. **Both "dead" flags were not dead** — they were *orphaned* by P0-1. `OUTREACH_AUDIT_LED`
   is read by `auto_outreach._audit_led_on()`; `OUTREACH_CAMPAIGN_VARIANTS` by the
   champion/challenger copy selector. Restoring `auto_outreach.py` re-reads both, so the
   gate now passes **legitimately** — no gate was weakened and no flag was deleted.

Also repaired: a byte-identical **duplicate `worker_id_for()`** definition (ruff F811),
5 typing/modernisation ruff errors, and a non-hermetic test
(`test_dev_workers_becomes_nonzero` asserted `len(prover.workers) == 1` against the shared
global ledger after a sibling test had already written `dw_task_full` into it).

### P0-4 — Secret hygiene verified 🟢

* `app/platform/typesafe_integration.py` — the hardcoded live key was **already removed** and
  the removal is in `origin/main` (commit `979c2229`, "remove 2 hardcoded live credentials +
  close the scanner hole that hid them").
* The removed value is still in **git history** (`7317f990`); its shape began `241d1117d…`
  (value intentionally NOT reproduced here). **Owner must rotate it.**
* Current tree: `scripts/check_secrets.py --all` →
  `[check_secrets] scanning 4273 files (ALL tracked files)` → **`[OK] no secrets detected`**.
* `GitGuardian Security Checks` = pass on PR #522.

---

## 3. VERIFICATION PERFORMED

| Check | Before | After |
| --- | --- | --- |
| `ruff check app/platform/dev_workers.py tests/test_dev_workers.py` | 7 errors (incl. F811) | **All checks passed** |
| `ruff check app/platform/auto_outreach.py` | n/a (file empty) | **All checks passed** |
| `pytest tests/test_auto_outreach.py tests/test_outreach_audit_led.py` | 13 failed + 13 collection errors | **39 passed** |
| `pytest tests/test_dev_workers.py` | 1 failed (never collected: BOM) | **11 passed** |
| `python scripts/prod_check.py` | `[FAIL] 3 problem(s)` | **`[OK] ALL CHECKS PASSED - ready to deploy`** |
| `scripts/check_secrets.py --all` | — | **[OK] no secrets detected** (4,273 files) |

Residual `prod_check` WARN (non-blocking): two orphan module trees — stale `.pyc` files with
no `.py` source (`app\voice_agent\swara_pitch_v2*.pyc`, 11 in `tests\`). These are ghosts from
an unmerged branch and must not be mistaken for live features.

---

## 4. OPEN FINDINGS — PRIORITIZED BACKLOG (NOT fixed this session)

| ID | Pri | Finding | Evidence | Next action |
| --- | --- | --- | --- | --- |
| B-1 | **P0** | **TypeSafe key must be rotated.** Removal is committed, but the value survives in git history (`7317f990`). | `git show 979c2229` (value withheld) | Owner rotates at `platform.typesafe.ai`; never persist to prod `.env`. |
| B-2 | **P0** | **Live prod still runs the broken image.** The restore is only on the branch, not deployed. | `docker ps` → all containers `:680722c8`; prod file is 0 bytes | Merge PR #522 → `bash scripts/deploy_vps.sh` → re-probe `/health`. |
| B-3 | **P0** | **`leadgen-call-loop.service` is `inactive dead`** while inside the TRAI 09:00–20:00 IST window → cold outbound calling is not running. | `systemctl list-units ... \| grep leadgen` | Confirm intended trigger (scheduler vs unit), then start + verify a real dial. |
| B-4 | **P0** | **`HQ_AUTO_CHASE` governance gap**: flag enabled with no runtime approval-ID/status enforcement (flagged in Wave-1, not yet contained). | Wave-1 doc §6; flag present in prod `.env` | Fail-closed: set `HQ_AUTO_CHASE=0`, restart, verify OFF, then design the approval gate. |
| B-5 | **P1** | **`VOBIZ_CALLER_ID` still present in prod `.env`** — Vobiz is supposed to be a removed provider path. | `ssh ... grep -oE '^[A-Z_]+=' /opt/leadgen/.env` | Prove no runtime consumer of `VOBIZ_CALLER_ID`, then remove the var + dead code. |
| B-6 | **P1** | **Graphify graph is STALE.** `app/graphify-out/GRAPH_REPORT.md` says `Built from commit: 20e4180b` (mtime 2026-09-14) vs HEAD `7bb050d4`. | `Select-String GRAPH_REPORT.md` | `scripts/graphify_refresh.sh --force` (`graphify.exe` is on PATH). |
| B-7 | **P1** | **Duplicate skill registries still exist.** ADR-131 declares `.claude/skills` (212 dirs) canonical and removed `.agents/skills`; but **`skills/` (4 skills, 10 tracked files — incl. `skills/typesafe-ai/SKILL.md`) and `.cursor/skills/leadgen-composer`** are still tracked, and `tests/test_skill_tree_canonical_guard.py` only guards `.agents/skills`. | `git ls-files skills` | Reconcile into the canonical root, then extend the canonical guard to cover `skills/` + `.cursor/skills`. |
| B-8 | **P1** | **`app/api/admin.py:674` imports a symbol that does not exist**: `from app.platform.auto_outreach import EmailSender as _ES`. `auto_outreach` only imports `EmailSender` *inside* functions from `app.integrations.email_sender`. The import sits in a best-effort `try`, so the admin-created-user verification email silently never sends. | `Get-Content app/api/admin.py \| Select -Skip 666 -First 16` | Point the import at `app.integrations.email_sender`. |
| B-9 | **P2** | **`data/orchestrator_ledger.db` is gitignored but was locally JSON-clobbered** by P0-2 before the fix. Any dev/CI machine that ran the old code has a corrupted local task ledger. | first bytes `7B 0D 0A ...` | Delete the corrupted local file so SQLite recreates it; confirm prod's real ledger path (not `/opt/leadgen/data/`). |
| B-10 | **P2** | **Stale 0-byte tracked files**: `memory/2026-09-04.md` and a tracked `$null`; plus test artifacts committed under `.pytest_tmp_*` and `._t_resume.txt`. | zero-byte sweep of tracked files | Triage and remove from tracking. |
| B-11 | **P2** | **GitHub ruleset 23507307 still lacks required status checks.** Live rules are only `deletion` + `non_fast_forward`. | Wave-1 doc §3 | `gh api -X PUT /repos/.../rulesets/23507307` with full JSON incl. required checks. |

## 5. OWNER-ONLY ACTIONS REQUIRED

1. **Rotate the TypeSafe API key** (B-1) — it is in git history; deleting the line did not un-expose it.
2. Approve the merge of PR #522 and the production deploy of the restored engine (B-2).
3. Decide the intended trigger for `leadgen-call-loop.service` (B-3).
4. Confirm the `HQ_AUTO_CHASE` containment decision (B-4).

## 6. ROLLBACK

* **P0-1:** `git checkout e69de29b -- app/platform/auto_outreach.py` (returns to the 0-byte state — only use if the restore itself regresses).
* **P0-2/P0-3:** `git revert 7bb050d4` — no data movement; the new JSON ledger path is additive.
* **Deploy:** canonical rollback lineage is `680722c8` (current prod image tag remains pullable).

## 7. ACCEPTANCE STATUS (honest labelling)

| Item | Status |
| --- | --- |
| `auto_outreach` restored in Git + CI | **TEST-PROVEN** (39 tests green, prod_check green) |
| `auto_outreach` restored in **production** | **NOT DONE — BLOCKED on merge + deploy** |
| dev_workers ledger collision | **CODE-PRESENT + TEST-PROVEN** |
| BOM / prod_check blockers | **TEST-PROVEN** |
| Secret hygiene (current tree) | **VERIFIED** (4,273 files, 0 findings) |
| Secret hygiene (history) | **BLOCKED on owner rotation** |
| SmartFlo-only calling | **NOT VERIFIED** (call loop inactive; `VOBIZ_CALLER_ID` still present) |
| 9 workers / 31 agents execution proof | **NOT CHECKED this session** |
| Graphify freshness | **STALE — not rebuilt** |

---
**Last updated:** 2026-09-18 ~13:35 IST · **Commits:** `344cb5e5`, `7bb050d4` on `fix/runtime-data-baseline-cline-0918` · **PR:** #522



