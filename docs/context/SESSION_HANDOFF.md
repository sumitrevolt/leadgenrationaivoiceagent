# SESSION_HANDOFF — overwrite every session end

## Session objective
Convert documented 31-agent system into real Agent Runtime capabilities + OpenClaw
observe path, without recreating existing kernel / Owner OS / touching Swara voice.

## Continuation outcome (2026-07-21)
- **PR #72** open (draft): `feat/agent-runtime-workforce-31` — workforce factory + Wave-B pilots
- **Local canary proof:** `pranav` = `canary_proven` (real-engine, local only)
- **Prod canary BLOCKED:** `/health` `7ce4d97` behind `origin/main` `10a3996`; branch `18b8d3e` not deployed; `AGENT_RUNTIME` unset on prod
- Other 11 pilots = `canary_ready`; 17 = `rollout_hold`; Swara+Ananya = `intentionally_disabled`

## Starting state
- Primary checkout `leadgenrationaiagent` DIRTY (skill deletions) — left untouched
- Isolated worktree: `C:\Users\Ratanshila\Documents\leadgen-agent-runtime-31`
- Branch: `feat/agent-runtime-workforce-31` @ tip `18b8d3e` (ahead of origin/main `10a3996`)
- Prod `/health.version` = `7ce4d97` (drift vs main)

## Discover
- Already present: `agent_registry` (31 contracts), `agent_runtime` kernel,
  pilots (kavya/isha/zara), OpenClaw→Owner OS, staff `run_*` wrappers
- Gap: only 3 pilots had capabilities; 28 registry-only; no workforce factory

## Changed (worktree only)
- `app/platform/agent_runtime_workforce.py` — factory: 31 caps, Swara frozen transfer,
  Wave-B engine wraps (reuse engineer_agents / delivery_assurance / infra_handler / staff)
- `app/platform/agent_runtime.py` — widen `PILOT_AGENTS` Wave-B; health `capability_ready_hold`
- `app/api/owner_os.py` — `ensure_workforce_registered` on runtime routes
- OpenClaw: `agents.unhealthy`, `runtime.status`, Swara `openclaw_transfer` on `agent.status`
- Tests: `tests/test_agent_runtime_workforce.py` + fix non-pilot assert agent
- Docs: `docs/agent_runtime/TRUTH_MATRIX.md`, `OPERATOR_RUNBOOK.md`,
  `docs/research/OPENCLAW_31_AGENT_RESEARCH.md`

## Verification
- pytest workforce+runtime+registry+openclaw: green (see progress)
- `prod_check.py` ALL CHECKS PASSED earlier (1166 routes)
- Local Pranav real-engine canary: proven
- Prod Stage A / AGENT_RUNTIME: **not** done (drift + deploy auth)
- Swara: ZERO voice file edits; RED still hard-off; OpenClaw transfer package only

## Protected
No `.env`, billing, calling enable, Swara/voice modules, primary dirty tree, prod deploy

## Exact next task
Clear prod drift (deploy auth) before any prod `AGENT_RUNTIME=1` canary; keep OpenClaw OFF;
calling stays off. Do not merge/deploy without owner go-ahead.
