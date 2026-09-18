# Wave 2 Execution Plan — 2026-09-18

## Context (Wave 1 Ledger Frozen)
- Prod SHA: `680722c8` (1 commit behind HEAD `c4547ab18a`)
- Delta: `.agents/skills` legacy tree removal (provenance alignment, not feature fix)
- Prod health: 43 containers, 12h+ uptime, environment=production
- DSH: runtime=1, shadow=1, allowlist=["jiya_makeover"]
- TypeSafe: code clean (commit 979c2229), but historical key in git history needs provider-side rotate
- CI: 5 lanes wired, ruleset 23507307 active (deletion+force-push protected), but required_status_checks NOT enforced
- DLQ: failed_tasks=1, dead=34
- Revenue: 1 customer (Jiya, ₹1,999/mo), target 5,002 additional customers for ₹1Cr MRR

## Wave 2 Priority Order

### 1. TypeSafe Old Key Provider-Side Revoke/Rotate 🔴 OWNER ACTION
- **What:** Revoke the ~100-char TypeSafe API key that was hardcoded in commit 7317f990
- **Evidence needed:** Rotation receipt from TypeSafe provider console
- **Note:** Code is clean (commit 979c2229). Git history rewrite is owner-gated separate decision. Rotation makes historical key harmless immediately.

### 2. GitHub Required-Status-Checks Enforcement ⚠️ OWNER ACTION
- **What:** Add `required_status_checks` to ruleset 23507307 binding 5 CI lanes:
  1. `Lint + syntax + secrets` (quality job)
  2. `prod_check runtime gates` (prod-check job)
  3. `Pytest Tests` (pytest-job job)
  4. `pip-audit installed env` (pip-audit job)
  5. `harness real-redis integration` (harness-redis-integration job)
- **Evidence needed:** Ruleset edit confirmation + intentionally failing PR shows merge blocked
- **Method:** GitHub UI or API `PATCH /repos/{owner}/{repo}/rulesets/{ruleset_id}`

### 3. DLQ Forensic (No Flush)
- **What:** Inspect `dlq:failed_tasks` (1 item) for root cause; sample/classify `dlq:dead` (34 items)
- **Evidence needed:** Task ID, error message, classification (transient vs permanent)
- **Command:** `redis-cli -n 0 lrange dlq:failed_tasks 0 -1` then decode payload
- **Note:** 34 dead tasks are trainer TimeLimitExceeded (pre-existing, non-blocking)

### 4. SmartFlo DID Console Gate
- **What:** Verify DID `918069879757` has destination assigned to VOICE Bot in Tata SmartFlo console
- **Evidence needed:** Screenshot or API response showing DID → VoIP/SIP endpoint binding
- **Note:** Repo evidence confirms this is the real telephony blocker — code path ready but destination must be configured in provider console

### 5. Deploy c4547ab18a
- **What:** Dry-run → canonical deploy → verify `/health.version` + worker image provenance + queue regression
- **Evidence needed:** `/health` `version: c4547ab18a`, all containers same image, celery queue still 0
- **Method:** `deploy_vps.sh` via SSH (canonical, owner-gated)
- **Note:** This is provenance alignment, not feature fix

### 6. One Controlled SmartFlo Call
- **What:** Place one test call within 09:00–20:00 IST window
- **Evidence needed:** CDR (call detail record), status=answered, transcript, recording URL
- **Method:** Admin test-call endpoint `POST /api/telephony/vobiz/test-call` (still mounted despite Vobiz removal) or SmartFlo direct C2C test
- **Compliance:** DND check pass, window check pass, DLT approved, AI disclosure spoken

### 7. Revenue Execution
- **What:** UPI bind + bank confirm + Hot Queue processing for 2nd customer
- **Evidence needed:** UPI VPA bound, bank credit recorded, customer invoice created (INV/2026-27/0002)
- **Acquisition economics:** Model tiered pricing (₹1,999 starter + ₹5,999 combo/advanced) to reduce customer count needed
- **Note:** 5,002 customers at ₹1,999 is baseline; mixed-tier model reduces count requirement

## Success Criteria (All Required)
1. ✅ TypeSafe rotation receipt/evidence
2. ✅ Merge blocked on red CI (prove ruleset works)
3. ✅ DLQ root cause known (not flushed)
4. ✅ SmartFlo DID destination non-null
5. ✅ Deployed SHA aligned (`c4547ab18a`)
6. ✅ One successful compliant SmartFlo call with CDR
7. ✅ Second verified payment/customer event

## Blockers (Owner-Only Actions)
- TypeSafe provider console access
- GitHub ruleset edit (admin)
- SmartFlo provider console (DID destination assignment)
- UPI bind + bank confirmation
- Deploy command execution

---
Created: 2026-09-18 05:10 IST
🐦 pelican