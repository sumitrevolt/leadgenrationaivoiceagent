# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Agent Runtime workforce Wave-B — IN PROGRESS
- **ID:** WS-1
- **Business outcome:** All 31 agents have real runtime capabilities; Wave-B GREEN dispatchable under `AGENT_RUNTIME`; Swara OpenClaw-observable without voice edits
- **Owner:** Platform
- **Branch / worktree:** `feat/agent-runtime-workforce-31` @ `C:\Users\Ratanshila\Documents\leadgen-agent-runtime-31`
- **Status:**
  - Draft **PR #72** open
  - Local canary **proven** (`pranav` real-engine)
  - Prod canary **blocked** on drift (`7ce4d97` behind `10a3996`) + deploy auth; `AGENT_RUNTIME` unset on prod
- **Acceptance:**
  - 31/31 capabilities registered ✓
  - Swara frozen transfer via OpenClaw `agent.status` (no voice edits) ✓
  - Wave-B pilots widened ✓
  - pytest green (runtime+workforce+registry+openclaw) ✓
  - prod_check PASS ✓
  - Local Pranav canary proven ✓
  - Prod deploy / `AGENT_RUNTIME` canary — BLOCKED (drift + deploy auth)
- **Next exact action:** Owner-authorized clear prod drift → then Stage A canary; do not merge/deploy without go-ahead

---

## WS-2 Jiya delivery assurance — PARKED
- External Meta/approvals

---

## WS-3 OpenClaw Owner Copilot — MERGED (prod flag OFF)
- Source on main; `OPENCLAW_ENABLED` default 0
- New GREEN cmds on this branch: `agents.unhealthy`, `runtime.status`
