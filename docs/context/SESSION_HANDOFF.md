# SESSION_HANDOFF — overwrite every session end

## Session objective
Convert documented 31-agent system into real Agent Runtime capabilities + OpenClaw
observe path, without recreating existing kernel / Owner OS / touching Swara voice.

## Starting state
- Primary checkout `leadgenrationaiagent` DIRTY (skill deletions) — left untouched
- Isolated worktree: `C:\Users\Ratanshila\Documents\leadgen-agent-runtime-31`
- Branch: `feat/agent-runtime-workforce-31` @ `origin/main` tip `10a3996a`
- Prod `/health.version` was `7ce4d979` (local main); origin/main ahead

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
- pytest workforce+runtime+registry+openclaw: re-run after cache clear (see progress)
- `prod_check.py` ALL CHECKS PASSED earlier (1166 routes)
- Swara: ZERO voice file edits; RED still hard-off; OpenClaw transfer package only

## Protected
No `.env`, billing, calling enable, Swara/voice modules, primary dirty tree, prod deploy

## Exact next task
Owner: review worktree → commit/PR when asked → Stage canary `AGENT_RUNTIME=1` + one
GREEN flag (e.g. `SRE_AGENT=1`) — no OpenClaw prod flip without auth; calling stays off
