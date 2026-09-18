# Wave 2 Execution Ledger — 2026-09-18

## Frozen State (Wave 1)
- Prod SHA: `680722c8`
- HEAD SHA: `c4547ab18a` (1 commit delta: legacy .agents/skills removal)
- Containers: 43 running, 12h+ uptime
- Environment: production
- DSH: runtime=1, shadow=1, allowlist=["jiya_makeover"]
- TypeSafe: code clean (commit 979c2229), historical key needs provider rotate
- CI: 5 lanes wired, ruleset 23507307 active (deletion+force-push protected), required_status_checks NOT enforced
- Revenue: 1 customer (Jiya, ₹1,999/mo), target 5,002 additional for ₹1Cr MRR

## Wave 2 Fixes Applied

### 1. Gated-Inert DLQ Semantic Bug (FIXED)
**Root cause:** 34 dead `video_delivery*` entries are FALSE POSITIVES.
- When `VIDEO_TELEGRAM_DELIVERY_ENABLED=0`, `team_scheduler._run_job` returns `ok=False` and records `status="gated_inert"`
- `staff_jobs.run_staff_job()` treated `ok=False` as failure → raised `RuntimeError`
- Celery retried 2x → `dlq:failed_tasks` → `dlq:dead` after 3 attempts
- **Result:** Intentionally gated-off jobs fill DLQ with false positives

**Fix:** `app/tasks/staff_jobs.py` line 485-495
```python
if ok is False:
    # Check gated_inert before raising
    try:
        from app.platform import automation_health as _ah_check
        if _ah_check.gated_inert(job):
            logger.info(f"[staff_jobs] job '{job}' gated-inert (flag OFF) — no retry")
            return {"ok": True, "job": job, "status": "gated_inert"}
    except Exception:
        pass
    raise RuntimeError(f"staff job '{job}' reported failure")
```

**Evidence:**
- Test: `tests/test_gated_inert_dlq_regression.py` — 3/3 PASS
- Acceptance criteria met:
  1. ✅ Gate OFF records `status=gated_inert, ok=False` in health/history
  2. ✅ `run_staff_job("video_delivery_retry")` returns `{"ok": True, "status": "gated_inert"}` — no retry
  3. ✅ Genuine `_run_job_inner=False` (non-gated) still raises `RuntimeError` → retry/DLQ
  4. ✅ No customer delivery occurs with flag OFF (gate check happens before execution)
  5. ✅ Regression test proves gated-inert jobs never enter `dlq:failed_tasks`

**Next step:** Deploy fix, observe 1 natural 15-minute retry tick, confirm no new DLQ entries, then classify/archival 34 historical dead rows.

### 2. TypeSafe Key Rotation (PENDING OWNER ACTION)
- Code clean (commit 979c2229 removed hardcoded key)
- Historical key exists in git history (commit 7317f990)
- **OWNER ACTION:** Revoke TypeSafe API key in provider console
- After revoke: historical key harmless, can consider history rewrite (owner-gated)

### 3. CI Required Status Checks (PENDING OWNER ACTION)
- Ruleset `23507307` active (deletion + non_fast_forward protection)
- **MISSING:** `required_status_checks` binding 5 CI lanes
- **OWNER ACTION:** Add required_status_checks to ruleset via GitHub UI/API
- Lanes to bind:
  1. `Lint + syntax + secrets` (quality job)
  2. `prod_check runtime gates` (prod-check job)
  3. `Pytest Tests` (pytest-job job)
  4. `pip-audit installed env` (pip-audit job)
  5. `harness real-redis integration` (harness-redis-integration job)

### 4. SmartFlo DID Verification (PENDING OWNER ACTION)
- DID: `918069879757`
- Code path ready: `TataSmartfloClient` → C2C API
- **OWNER ACTION:** Confirm DID destination assigned to VOICE Bot in Tata SmartFlo console
- This is the real telephony blocker (not code)

### 5. Deploy to Production (READY)
- Current HEAD: `c4547ab18a` (local)
- Provenance alignment: legacy `.agents/skills` removal
- **Method:** `deploy_vps.sh` via SSH (canonical, owner-gated)
- **Verify:** `/health.version` = `c4547ab18a`, all containers same image, celery queue still 0

### 6. Controlled SmartFlo Call (POST-DEPLOY)
- **Prerequisite:** DID destination assigned (step 4)
- **Method:** Test call within 09:00–20:00 IST window
- **Evidence needed:** CDR, status=answered, transcript, recording URL
- **Compliance:** DND pass, window pass, DLT approved, AI disclosure spoken

### 7. Revenue Execution (OWNER ACTION)
- UPI bind + bank confirm
- Hot Queue `/app/inbox` authenticated walkthrough
- 2nd customer invoice: `INV/2026-27/0002`
- Acquisition economics: model mixed-tier (₹1,999 starter + ₹5,999 combo/advanced)

## DLQ State (Pre-Fix)
```
dlq:failed_tasks: 2 items
  - 3bdd9989: video_delivery_retry @ 23:34 UTC — failure
  - 3b3ba45c: video_delivery_retry @ 23:19 UTC — failure

dlq:dead: 34 items
  - All video_delivery/video_delivery_retry
  - All: "max 3 auto-retries exhausted"
  - Timestamps: 2026-09-17 22:00–23:00 UTC
  - Classification: FALSE POSITIVES (gated-off jobs)
```

## Wave 2 Success Criteria Status
- [ ] TypeSafe rotation receipt — PENDING OWNER
- [ ] Merge blocked on red CI — PENDING OWNER (ruleset edit)
- [x] DLQ root cause known — FIXED (gated-inert semantic bug)
- [ ] SmartFlo DID destination — PENDING OWNER (console action)
- [ ] Deployed SHA aligned — READY (c4547ab18a + fix)
- [ ] One successful SmartFlo call — PENDING (DID assignment)
- [ ] Second verified payment — PENDING OWNER (Hot Queue)

---
Created: 2026-09-18 05:20 IST
Fixed by: Autonomous Admin Wave 2
🐦 pelican