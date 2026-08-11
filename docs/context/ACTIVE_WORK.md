# ACTIVE_WORK - max 3 workstreams

---

## WS-GOV Boss + Second Brain decision governance (CURSOR)
- **ID:** WS-GOV
- **Business outcome:** Decision-bearing STAFF outputs require Second Brain advice + Boss/Owner gates before execute; no parallel approval plane
- **Current state:** Worktree `C:\Users\Ratanshila\Documents\leadgen-boss-second-brain-governance-20260811` · branch `cursor/boss-second-brain-governance-20260811` · base merge SHA **`6052b533`** (PR #329). Module + 14 tests + Owner OS visibility + Buzz RO + runbook. Flag `BOSS_DECISION_GOVERNANCE` OFF default.
- **Next exact action:** Draft PR green → owner AUTH-MERGE (separate); no prod flag arm; no deploy
- **Out of scope:** Voice/Swara · UPI auto · provider canaries · second Boss/ledger

---

## WS-BUZZ Local Buzz Desktop + relay (CURSOR)
- **ID:** WS-BUZZ
- **Business outcome:** Owner→Boss visibility plane on local `ws://127.0.0.1:3000`; Buzz never prod mutation executor
- **Current state:** `buzz-prod` relay healthy on **:3000** (remapped from 3100; volumes unchanged). Desktop running. LIVE Boss prefix **`20b69265`**. Correlated `@Boss` response **WAIT — OWNER INTERACTIVE BUZZ AUTH** (harness/membership on local relay).
- **Next exact action:** Owner Desktop Save/start Boss harness on local relay; ≥600s mention proof
- **Out of scope:** `-ResetData` · history wipe · Comb before Boss proof · prod/#admin mutation

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
