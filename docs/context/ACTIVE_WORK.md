# ACTIVE_WORK - max 3 workstreams

---

## WS-CONTAIN1 REPLY_AUTO_SEND_HARD_OFF Option A - IN FLIGHT (owner-locked)
- **ID:** WS-CONTAIN1
- **Business outcome:** Restore SAFETY_INVARIANT kill switch — stop live auto-sends; Redis `reply_auto_send` can stay but HARD_OFF must win
- **Current state:** Owner verdict Option A locked. Prod `/health`=`a08dd5e9`. Cloud has **no VPS SSH**. Local Cursor executing `.env` HARD_OFF=1 + recreate app+worker @ `APP_VERSION=a08dd5e9`. PR #276 deploy **blocked** until `enabled=False` evidence.
- **Next exact action:** Local Cursor posts HARD_OFF proof (`_reply_auto_send_enabled()` → False) → then merge+deploy #276 via `deploy_vps.sh` + VOICE_LAUNCH_KILL dance
- **Out of scope:** Option B · flipping `REPLY_AUTO_SEND` · WI-CP2 tonight · side-effect run-now · secrets in chat

---

## WS-NAV1 PR #276 Master Blueprint admin nav - GATED ON CONTAINMENT
- **ID:** WS-NAV1
- **Business outcome:** Admin System nav + quick action door to Master Blueprint (`/app/explorer?view=master`)
- **Current state:** OPEN MERGEABLE · commit `8b36b795` · branch `fix/admin-master-blueprint-nav` · acceptance currently `grep -c -i "master blueprint"` = 0 on `/app/admin`
- **Next exact action:** AFTER HARD_OFF evidence only — merge + `deploy_vps.sh` with APP_VERSION pin (rides #275 safe_settings on main tip)
- **Out of scope:** deploy before containment · env flips inside this PR

---

## WS-GTM1 Hot Queue → 2nd paid - REVENUE PENDING
- **ID:** WS-GTM1
- **Current state:** HQ empty; owner prospect pick
- **Next exact action:** Real ₹1999 UPI → LEDGER_PAID
- **Out of scope:** fake PAID

---

## Parked
- WS-PRF1 PR Factory (was in-flight; parked behind containment)
- WS-GTM2 Admin Manual Call canary
- WS-AM1 Safe Pack (after LEDGER_PAID)
- WI-CP2 interaction-log (when auto-send re-armed)
- Estique `removed`
