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
- **Current state:** CODE-LIVE `a3fbc8bb` (PR #320) · WAIT first live proof
- **Next exact action:** Wait for first guest payment (or staging simulate)
- **Out of scope:** Deploy · changing UPI flow

---

## WS-SEC Security/compliance residual (CURSOR LANE B)
- **ID:** WS-SEC
- **Business outcome:** All compliance gates (DND/TRAI/DPDP/secrets) remain fail-closed while voice stays frozen
- **Current state:** Gates INTACT · voice/Swara FROZEN · DSH code LIVE-INERT on `fb3d0bc2` (flags OFF, no dsh-worker)
- **Next exact action:** Monitor only; no voice edits and no gate weakening
- **Out of scope:** Voice/Swara edits · weakening compliance gates · arming DSH

---

## Parked (not in active 3)
- **WS-DSH** Hardened DeepSeek Harness CODE-READY/INERT AUTH-DEPLOYED on prod `fb3d0bc2` via PR #361. Runtime/shadow OFF. No canary/retirement without separate owner auth.
- **WS-HYG** Duplicate/docs hygiene — AUTH-DEPLOYED ancestry of `fb3d0bc2` (via #356/`150bf898`). COMPLETE.
- **WS-DSH180** ADR-180 SessionEvent steal remains LIVE-INERT (`HARNESS_SESSION_EVENTS` UNSET). Do not arm.
- **WS-GOV** Boss + Second Brain governance (PR #330 MERGED `8f5a2e2d`, prod has ancestry, flag OFF)
- **WS-BUZZ** Local Buzz Desktop + relay (Cursor ACP Boss canonical `1b13cecc`, relay verified)
- **WS-DEP329** Rollback retention lineage
- **WS-REV** #306 live proofs (after #304 guest bind proven)
- **WS-AMAX** DUNNING safe-enabler (#307 stays OFF per owner decision)
- **WS-SEC1** Vobiz credential rotation
- Creative OS expansion · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
