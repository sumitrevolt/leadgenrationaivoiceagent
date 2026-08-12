# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid (CURSOR LANE B)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** Technical READY · All routes LIVE · Owner outreach execution blocking only · Evidence `docs/evidence/REVENUE_READY_20260812.md`
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
- **ID:** WS-GOV
- **Business outcome:** Decision-bearing STAFF outputs require Second Brain advice + Boss/Owner gates before execute; no parallel approval plane
- **Current state:** PR #330 Ready · head **`8f5a2e2d`** · base **`6052b533`**. Cursor ACP Boss canary GO · Comb findings fixed · CI green. Flag `BOSS_DECISION_GOVERNANCE` OFF. Second Brain vault `C:\Users\Ratanshila\Documents\leadsgenai-brain`.
- **Next exact action:** Owner AUTH-MERGE `8f5a2e2d…` PR #330 (normal merge only); no prod flag arm; no deploy
- **Out of scope:** Voice/Swara · UPI auto · provider canaries · second Boss/ledger

---

## WS-BUZZ Local Buzz Desktop + relay (CURSOR)
- **ID:** WS-BUZZ
- **Business outcome:** Owner→Boss visibility plane; Buzz never prod mutation executor
- **Current state:** Canonical Boss **`1b13cecc…`** · runtime **Cursor ACP** · relay auth + correlated canary **GO** (`BOSS-CURSOR-ACP-CANARY-…54b3cbb4`).
- **Next exact action:** Keep Cursor ACP as Boss harness; no duplicate Boss
- **Out of scope:** `-ResetData` · history wipe · Claude/Goose/Codex Boss fallback · prod flag arm

---

## WS-DEP329 Rollback retention deploy boundary (CURSOR)
- **ID:** WS-DEP329
- **Business outcome:** PR #329 lineage-aware image retention merged; prod deploy only on explicit AUTH-DEPLOY
- **Current state:** MERGED `6052b533`; prod still **`9b09a808`**. Request line ready: `AUTH-DEPLOY 6052b533f59e8ab533ab629427fa869d83931a9a`
- **Next exact action:** Owner issues AUTH-DEPLOY when ready; use `deploy_vps.sh` only
- **Out of scope:** Deploy under current AUTH · closing #307 · arming DUNNING

---

## Parked (not in active 3)
- **WS-GOV** Boss + Second Brain governance (PR #330 MERGED `8f5a2e2d`, prod has ancestry, flag OFF)
- **WS-BUZZ** Local Buzz Desktop + relay (Cursor ACP Boss canonical `1b13cecc`, relay verified)
- **WS-DEP329** Rollback retention (MERGED `6052b533`, prod `9c47647c` includes ancestry)
- **WS-REV** #306 live proofs (after #304 guest bind proven)
- **WS-AMAX** DUNNING safe-enabler (#307 stays OFF per owner decision)
- **WS-SEC1** Vobiz credential rotation
- Creative OS expansion · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
