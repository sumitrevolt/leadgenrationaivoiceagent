# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid (CURSOR LANE B)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** Technical READY · checklist `docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md` · Evidence `docs/evidence/REVENUE_READY_20260812.md` + live `ready_for_first_paid_customer=true`
- **Next exact action:** Owner daily Hot Queue blitz (15–30 min at `/app/inbox`) + UPI approval when payment arrives
- **Out of scope:** Flag arm · cold WA auto · lead magnet ads (see WS-REV50)

---

## WS-REV50 Product-1 → 50 paid/day capacity (90d)
- **ID:** WS-REV50
- **Business outcome:** Build capacity toward 50 new ₹1,999/mo Marketing subscribers / day
- **Current state:** Plan artifact `docs/gtm/PRODUCT1_50_PAID_DAY_90D.md` · Phase 0 in progress via WS-GTM1 · not claiming 50/day live
- **Next exact action:** After 2nd paid, owner sets ads budget + GSC creds decision for Phase 1
- **Out of scope:** Weakening compliance · Stripe/Razorpay return · inventing metrics

---

## WS-SEC Security/compliance residual (CURSOR LANE B)
- **ID:** WS-SEC
- **Business outcome:** Compliance gates stay fail-closed; voice frozen; DSH kill switch practiced
- **Current state:** Gates INTACT · voice/Swara FROZEN · DSH LIVE-AUTHORITY 29 on `fb3d0bc2` (rollback drill green)
- **Next exact action:** Monitor DSH worker health + queues; kill = `DSH_RUNTIME_ENABLED=0` if needed
- **Out of scope:** Voice/Swara edits · gate weakening · legacy executor deletion

---

## Parked (not in active 3)
- **WS-DSH** Armed under ADR-183 owner override (was CODE-READY/INERT). Shadow soak / wave order skipped by owner. Retirement still blocked.
- **WS-UPI304** Guest bind CODE-LIVE — wait first live proof
- **WS-HYG** COMPLETE on `fb3d0bc2` ancestry
- **WS-DSH180** SessionEvent still UNSET — do not arm with AGENT_HARNESS
- **WS-GOV** Boss governance flag OFF
- **WS-BUZZ** Local Buzz relay
- **WS-DEP329** Rollback retention lineage
- **WS-REV** #306 after #304 proof
- **WS-AMAX** Dunning OFF
- **WS-SEC1** Vobiz rotation
- Creative OS · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
