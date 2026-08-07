# ACTIVE_WORK - max 3 workstreams

---

## WS-CONTAIN1 REPLY_AUTO_SEND_HARD_OFF Option A - DONE (ADR-170)
- **ID:** WS-CONTAIN1
- **Business outcome:** SAFETY_INVARIANT kill restored; live auto-sends stopped
- **Current state:** PRODUCTION-PROVEN on `7ab5fe55` — HARD_OFF=1, enabled()=False. ADR-170 supersedes ADR-169. Matrix row 22 = HARD-OFF RESTORED. **Do not re-flip.**
- **Next exact action:** None for containment. WI-CP2 only if/when auto-send re-armed later.
- **Out of scope:** Option B · REPLY_AUTO_SEND flip · redeploy · secrets

---

## WS-NAV1 PR #276 Master Blueprint admin nav - DONE LIVE
- **ID:** WS-NAV1
- **Business outcome:** Admin System nav door to Master Blueprint
- **Current state:** MERGED+DEPLOYED `/health`=`7ab5fe55`; 5/5 skew 0; VOICE_LAUNCH_KILL=0 restored; admin Master Blueprint count **4** (PASS)
- **Next exact action:** None
- **Out of scope:** re-deploy

---

## WS-GTM1 Hot Queue → 2nd paid - REVENUE PENDING
- **ID:** WS-GTM1
- **Current state:** HQ empty; owner prospect pick
- **Next exact action:** Real ₹1999 UPI → LEDGER_PAID
- **Out of scope:** fake PAID

---

## Parked
- WI-CP2 interaction-log (when auto-send re-armed)
- WS-PRF1 PR Factory
- WS-GTM2 Admin Manual Call canary
- WS-AM1 Safe Pack (after LEDGER_PAID)
- Estique `removed`
