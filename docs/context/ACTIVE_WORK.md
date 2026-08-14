# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid (CURSOR LANE B)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** Technical READY · CODE-PRESENT this session: admin/inbox/marketing "Aaj" path Hot Queue pe; owner outreach + UPI confirm still the revenue gate · Evidence `docs/evidence/REVENUE_READY_20260812.md` + live 2026-08-14 `ready_for_first_paid_customer=true`
- **Next exact action:** Owner daily Hot Queue blitz (15 min/day at `/app/inbox`) + UPI approval when payment arrives
- **Out of scope:** Deploy · flag arm · lead magnet traffic generation

---

## WS-UPI304 Guest bind status (CURSOR LANE B)
- **ID:** WS-UPI304
- **Business outcome:** Guest (no login) can pay → admin binds client_id → activates subscription (resolves #304 approved_but_unbound)
- **Current state:** CODE-LIVE `a3fbc8bb` (PR #320) · TEST-PROVEN `test_upi_guest_bind_workflow_2026_08_10.py` · UI wired `admin_dashboard.html` · WAIT first live proof
- **Next exact action:** Wait for first guest payment (or simulate staging) to prove live workflow
- **Out of scope:** Deploy (already live) · changing UPI flow

---

## WS-SEC Security/compliance residual (CURSOR LANE B)
- **ID:** WS-SEC
- **Business outcome:** All compliance gates (DND/TRAI/DPDP/secrets) remain fail-closed; voice FROZEN
- **Current state:** Gates INTACT · Voice FROZEN per constraint · No security regressions
- **Next exact action:** Monitor only; no changes permitted
- **Out of scope:** Voice/Swara edits · weakening compliance gates

---

## Parked (not in active 3)
- **WS-HYG** Duplicate/docs hygiene 2026-08-14 — playbook templates + root orphans + deploy footguns archived; evidence `docs/evidence/HYGIENE_MERGE_20260814.md`. COMPLETE this session.
- **WS-DSH** ADR-179 NO-GO vendor; ADR-180 steal #1 CODE-PRESENT INERT (`HARNESS_SESSION_EVENTS=0`) — typed SessionEvent + hash-chain. Do not arm in prod.
- **WS-GOV** Boss + Second Brain governance (PR #330 MERGED `8f5a2e2d`, prod has ancestry, flag OFF)
- **WS-BUZZ** Local Buzz Desktop + relay (Cursor ACP Boss canonical `1b13cecc`, relay verified)
- **WS-DEP329** Rollback retention (MERGED `6052b533`)
- **WS-REV** #306 live proofs (after #304 guest bind proven)
- **WS-AMAX** DUNNING safe-enabler (#307 stays OFF per owner decision)
- **WS-SEC1** Vobiz credential rotation
- Creative OS expansion · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
