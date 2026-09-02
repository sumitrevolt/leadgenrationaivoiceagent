# Root-Cause Diagnostic — "Project not working as expected" (2026-06-27)

> **Trigger:** User report — "LeadGen AI project not working as expected; agents/workflows disconnected lag rahe."
> **Method:** Measure-first (project's own gates) — NO guessing. Static wiring gates + live VPS runtime liveness checks.
> **Verdict:** **System healthy, fully wired, and actively running.** The "disconnected" feeling is a **source-of-truth / documentation-drift problem, NOT a code break.**

---

## 1. Root Cause Report

**Symptom:** "Agents/workflows disconnected; system underperforming."

**Actual root cause:** A **visibility / source-of-truth gap**, not a functional failure.
- The codebase is large (~957 source files, ~947 routes, 24+ scheduled jobs, 190 automation flags, 17 AI staff).
- Several authoritative docs had **drifted** from live truth (notably pricing in `PROJECT_HANDOFF.md` showed old ₹1,199/₹6,999 + public Growth, while live `packages.py` is 2-plan ₹1,999 + Combo ₹5,999, Growth hidden).
- Without a single fresh entry-point, a human OR an AI agent (Claude/Codex) reading the repo gets a "nothing connects / I can't find the truth" feeling — which reads as "broken" even though every component is wired and firing.

**Evidence the system is actually fine (measured, not assumed):**

| Layer | Gate | Result |
|---|---|---|
| Live app | `GET https://leadsgenai.in/health` | `{"status":"healthy","environment":"production"}` |
| Static wiring | `scripts/prod_check.py` | 947 routes · **40 pages 0 gaps** · **automation 0 gaps** · explorer 239 nodes **0 orphans** · engine coverage **74/74** · 332 edges · **ALL CHECKS PASSED** |
| Frontend↔API | `scripts/deep_wiring_audit.py` | handlers=0 apis=0 anchors=0 → **0 gaps** |
| Automation graph | `scripts/automation_wiring_audit.py` | 190 flags **0 never-read** · 35 staff jobs **0 not-dispatchable** · 36 beat-tasks **0 unrecognized** |
| **Runtime (VPS)** | `docker compose ps` | `leadgen_worker` **Up (healthy)** · `leadgen_scheduler` **Up (healthy)** · app/db/redis/pgbouncer healthy |
| **Runtime queue** | `redis-cli llen celery` | **0** (not backed up) |
| **Runtime loop** | `data/job_heartbeats.json` mtime | **~16 seconds old** — dead-man loop actively ticking |

> Critical distinction the audit confirmed: **"dispatchable" ≠ "dispatched."** Static gates only prove the graph is wired. The VPS runtime checks above prove the automation is *actually firing* — both are green.

---

## 2. Broken Modules List

**None.** No broken module, dead worker, stuck queue, missing table, orphan agent, or frontend↔backend route mismatch was found by any of the six gates above.

What WAS found (non-code, documentation drift):

| Item | Type | Severity | Fixed? |
|---|---|---|---|
| `PROJECT_HANDOFF.md` §2 pricing (₹1,199/₹6,999, public Growth) | Doc drift | Medium (misleads humans + AI) | ✅ Fixed → 2-plan ₹1,999 + Combo ₹5,999, Growth hidden |
| `ARCHITECTURE.md` §5 telephony window "10am–7pm" | Doc drift | Low | ✅ Fixed → 9am–7pm |
| `ARCHITECTURE.md` / `WORKFLOW_MAPS.md` "Updated 2026-06-20" + no runtime-verification note | Staleness | Low | ✅ Refreshed |
| `PRODUCTION_CHECKLIST.md` missing | Missing doc | Low | ✅ Created (points to real gates) |
| `E2E_TEST_PLAN.md` missing | Missing doc | Low | ✅ Created (points to real 220-file suite) |

---

## 3. Fix Plan

Because the root cause is documentation/visibility (not code), the fix is **doc-only — no code change, no new system** (honoring "do not create duplicate systems" + "fix only real issues"):

1. ✅ Correct the pricing drift in `PROJECT_HANDOFF.md` to live `packages.py` truth.
2. ✅ Correct the telephony-window drift + refresh dates in `ARCHITECTURE.md` / `WORKFLOW_MAPS.md`.
3. ✅ Create the two missing source-of-truth docs (`PRODUCTION_CHECKLIST.md`, `E2E_TEST_PLAN.md`) as **thin indexes that point to the real gates/tests** — not parallel content that will drift again.
4. ✅ This report as the durable answer to "is my system actually working?" (yes — with proof).
5. **No code fix required.** `.env.example` (06-26) already current → left as-is.

---

## 4. Files Changed

| File | Change |
|---|---|
| `docs/PROJECT_HANDOFF.md` | §2 pricing table + 4 tier headers + trial note → current 2-plan/Combo truth; header date-note |
| `docs/ARCHITECTURE.md` | §5 calling-window 10am→9am; Updated date + runtime-verified note |
| `docs/WORKFLOW_MAPS.md` | Runtime-liveness verified note |
| `docs/DIAGNOSTIC_ROOT_CAUSE_2026_06_27.md` | **NEW** — this report |
| `docs/PRODUCTION_CHECKLIST.md` | **NEW** — lean launch/ship checklist → real gates |
| `docs/E2E_TEST_PLAN.md` | **NEW** — pipeline-stage → real test-file map |

---

## 5. Tests Added

No code changed, so no new unit/integration test is warranted (adding a test for a doc edit = noise). Pricing truth is **already guarded** by the existing `tests/test_billing_truth_2026.py` (CI-blocking) — that gate is what keeps `packages.py` and downstream in sync. The real "test" performed here was the **6-gate live diagnostic** documented in §1, reproducible any time via:

```bash
python scripts/prod_check.py
python scripts/deep_wiring_audit.py
python scripts/automation_wiring_audit.py
# VPS runtime: docker compose -f docker-compose.vps.yml ps + redis-cli llen celery + heartbeat mtime
python scripts/automation_health_audit.py --daily-check   # local helper
```

---

## 6. Final Production-Readiness Checklist (snapshot 2026-06-27)

| # | Check | Status |
|---|---|---|
| 1 | Live `/health` = production healthy | ✅ |
| 2 | Static wiring (prod_check) — 0 gaps, 0 orphans, 74/74 engines | ✅ |
| 3 | Frontend↔API wiring — 0 gaps | ✅ |
| 4 | Automation flags wired + jobs dispatchable | ✅ |
| 5 | Worker + scheduler containers Up (healthy) | ✅ |
| 6 | Celery queue not flooded (llen=0) | ✅ |
| 7 | Dead-man heartbeat fresh (<10 min) | ✅ |
| 8 | Pricing source-of-truth (`packages.py`) ↔ docs in sync | ✅ (fixed today) |
| 9 | Payments — UPI LIVE (`ready_for_first_paid_customer`) | ✅ |
| 10 | Voice cold-calling | ⛔ Externally blocked — DLT (Udyam re-apply) + Vobiz recharge+DID (user paperwork, NOT a code bug) |

**Bottom line:** Product-1 (Marketing) is production-ready and sellable today. Product-2 (Voice) is code-ready but commercially blocked on user paperwork. The platform is not "broken" — the real lever is **GTM / first paid customer**, consistent with prior audits.

---

*Generated by root-cause audit — measure-first, no guessing. See `PROJECT_HANDOFF.md` for full context.*
