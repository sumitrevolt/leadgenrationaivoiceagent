# ACTIVE_WORK - max 3 workstreams

---

## WS-GOV Boss + Second Brain decision governance (CURSOR)
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
- **WS-REV** #304 / #306 live proofs WAIT
- **WS-AMAX** DUNNING safe-enabler (prior worktree; #307 stays OFF)
- **WS-SEC1** Vobiz credential rotation
- **WS-GTM1** Hot Queue → 2nd paid
- Creative OS expansion · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
