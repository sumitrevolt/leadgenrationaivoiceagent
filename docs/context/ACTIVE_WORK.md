# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid (CURSOR LANE B)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** LIVE on `91958c23` (re-probed 2026-08-15 ~00:01Z, 5/5 pinned, VLK=0) · daily owner ntfy wired · checklist `docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md` · activation summary still `ready_for_first_paid_customer=false` (`blocker_count=1`, unchanged from `c4fc0087`) — owner blitz still the money path. **Technical money path = GO; REVENUE GENERATED = WAIT** until owner-confirmed UPI bank credit (verdict block in `CURRENT_STATE.md`). Aaj ka `paid_today=0` empty-day truth hai, defect nahi
- **Next exact action:** Owner daily Hot Queue blitz (15–30 min at `/app/inbox`) + UPI Bind/re-Approve when payment arrives. **Naya module/agent/loop tab tak nahi** jab tak koi correlated real-funnel defect evidence ke saath na mile
- **Out of scope:** Flag arm · cold WA auto · lead magnet ads (see WS-REV50)

---

## WS-REV50 Product-1 → 50 paid/day capacity (90d)
- **ID:** WS-REV50
- **Business outcome:** Build capacity toward 50 new ₹1,999/mo Marketing subscribers / day
- **Current state:** Plan `docs/gtm/PRODUCT1_50_PAID_DAY_90D.md` · Phase 0 via WS-GTM1 · UPI actionable-queue leak fixed on prod · **Phase 1 north-star KPI ab measurable — PR #363 LIVE on `91958c23`: ledger-backed `paid_today` / `activations_today` / `paid_gross_today_inr` on the admin "Aaj" snapshot (invoice + UPI ledgers, IST day, client+day dedupe, read-only). Baseline reading on deploy day = 0/0 (honest ledger answer, not a bug).** Not claiming 50/day live
- **Next exact action:** After 2nd paid, owner sets ads budget + GSC creds decision for Phase 1 — `paid_today` is now the scoreboard for that decision
- **Out of scope:** Weakening compliance · Stripe/Razorpay return · inventing metrics

---

## WS-SEC Security/compliance residual (CURSOR LANE B)
- **ID:** WS-SEC
- **Business outcome:** Compliance gates stay fail-closed; voice frozen; DSH kill switch practiced
- **Current state:** Gates INTACT · voice/Swara FROZEN · DSH LIVE-AUTHORITY 29 on `91958c23` · kill fence practiced again (PR #363 deploy; VLK proved TRUE mid-deploy, back to 0 after)
- **Next exact action:** Monitor DSH worker + queues; kill = `DSH_RUNTIME_ENABLED=0` if needed
- **Out of scope:** Voice/Swara edits · gate weakening · legacy executor deletion

---

## Parked (not in active 3)
- **WS-DSH** Armed under ADR-183; code+hotfix now on `c4fc0087`. Retirement still blocked.
- **WS-UPI304** Guest bind CODE-LIVE + approved-unactivated now stays in admin queue on `c4fc0087`
- **WS-HYG** COMPLETE in ancestry
- **WS-DSH180** SessionEvent still UNSET — do not arm with AGENT_HARNESS
- **WS-GOV** Boss governance flag OFF
- **WS-BUZZ** Local Buzz relay
- **WS-DEP329** Rollback retention lineage
- **WS-REV** #306 after #304 live proof
- **WS-AMAX** Dunning OFF
- **WS-SEC1** Vobiz rotation
- Creative OS · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
