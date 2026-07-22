# Arnav — Fourth-Agent Production Canary Proof

**Classification:** `PRODUCTION-CANARY-PROVEN` for Arnav `run_owned_workflow` → `engineer_agents.run_security`.  
**Date:** 2026-07-22 · **SHA:** `3fe74095` · **Outcome:** COMPLETE (this loop).  
Arnav **not** production_enabled — flags OFF after proof.

## Contract
`arnav` / `run_owned_workflow` / `arnav_security` / `run_security` / `SECURITY_AGENT` / GREEN / read_only / `OPS_ALERTS=0` during canary.

## Highlights
- Empty → `{arnav}` flag-only → armed `{arnav}` only
- Run `art_5aa08e56b9ce`, cmd `ocmd_63be2bc9cefa`, 391ms, score 67.5, secret_scan=0, ntfy=0
- Concurrent idem: app `art_3182e32905b9` / worker `duplicate_in_progress`
- Pause/stop/drain/kill + pre-engine cancel proven; cross-container cancel race not re-timed
- Scheduler IST 09:30–10:30; canary ~13:05 IST outside window; flag OFF before next trigger
- Rollback all OFF incl. `OPS_ALERTS=0` (pre had OPS_ALERTS=1; left OFF per auth)
- Counts: proven **4** / canary_ready **8** / hold 17 / disabled 2 = 31

Full detail: worktree `leadgen-dist-idem/docs/agent_runtime/ARNAV_PRODUCTION_CANARY_PROOF.md`
