# ADR-173 — claw-orchestrator (Enderfga): NO full vendor; patterns-only

- **Date:** 2026-08-08
- **Status:** ACCEPTED (evaluation-complete; no runtime merge)
- **Evaluated:** https://github.com/Enderfga/claw-orchestrator (`@enderfga/claw-orchestrator` **v4.11.0**, MIT)
- **Local eval clone (outside product tree):** `/tmp/claw_orch_eval/claw-orchestrator` (shallow; delete anytime)
- **Extends:** ADR-148, ADR-149, ADR-155, ADR-163, ADR-172, ADR-OPENCLAW-OWNER-COPILOT

## Context

Marketing pitch: claw-orchestrator wraps Claude Code + Codex + Gemini/agy + Cursor Agent +
OpenCode as one headless runtime, with first-class OpenClaw plugin support, parallel agents
in git worktrees, MCP exposure, council/autoloop/ultraapp. LeadGen already runs OpenClaw
Stage A and has `external_agents` + PR Factory + ADR-172 Agent Teams worktrees — so the
diagram *looks* like a natural fit.

That diagram match is real. The **authority model is not**.

## Evidence from the package (not marketing)

| Fact | Source | Conflict with LeadGen |
|------|--------|------------------------|
| Install path = `npm i -g` + rewrite `~/.openclaw/openclaw.json` plugin paths | `install.sh` | Sidesteps LeadGen typed command allowlist; gateway-level tool dump |
| Getting-started uses `openclaw plugins install … --dangerously-force-unsafe-install` | `skills/references/getting-started.md` | Explicit unsafe install posture |
| Plugin advertises **65 tools** (`session_start`, `council_*`, `ultraapp_*`, container start/stop, …) | `openclaw.plugin.json` contracts.tools | OpenClaw Stage A today exposes only GREEN observe (`external.missions`, `external.mission_status`) |
| Capability `childProcess: true` | `openclaw.plugin.json` | Coding CLIs become spawnable from OpenClaw agents — second dispatcher |
| Default `defaultPermissionMode: acceptEdits`; council docs default **`bypassPermissions`** | plugin configSchema + `council.md` | Opposite of fail-closed Owner OS / R8 frozen surfaces |
| Council rule “Never ask permission, just work” | `council.md` §7 Action Over Words | Explicitly conflicts AGENT_WORK_RULES R8 |
| Separate HTTP dashboard + server (`clawo serve`, :18796) + Ultraapp forge containers | README / tools | Second product surface beside Owner OS / Dev Control |
| Node ≥22 TypeScript runtime | `package.json` engines | Not our Python/FastAPI/Celery control plane |
| OpenAI-compat proxy + multi-model proxy (Gemini defaults) | README / plugin proxy block | Paid/BYOK gravity; free-stack mandate for OpenCode path |
| Own session/council ledger under `~/.openclaw/` | docs | Second mission store vs `external_agents` Mission JSON + CAS |

LeadGen locked architecture (ADR-OPENCLAW):

```text
Admin → OpenClaw Copilot → Owner OS → Boss → 31 STAFF → Celery
```

OpenClaw is an **inbound edge**, not a coding runtime that spawns CLIs. Coding missions
belong to `app/dev_control/external_agents/` (leases, path ownership, executor≠reviewer,
GREEN/AMBER/RED). Workforce stays **31** — claw-orchestrator does not become a 32nd agent
and must not become a parallel dispatcher.

## Decision

**REJECT full install / subtree / OpenClaw plugin registration / `clawo serve` in prod or
as the coding control plane.**

**ALLOW FEATURE_HARVEST only** — copy *ideas* into existing surfaces:

| Idea from claw-orchestrator | Canonical LeadGen home |
|-----------------------------|-------------------------|
| Multi-engine CLI session wrapper | `external_agents/runner/*` (already Claude + Cursor) |
| Worktree-isolated parallel workers | ADR-172 `scripts/agent_team_worktree.py` + runner worktrees |
| Bounded MCP tool allowlist (`CLAWO_MCP_TOOLS` pattern) | Future: MCP expose of **read-only** mission status — never 65 write tools |
| Planner / Coder / Reviewer separation | Already: executor ≠ reviewer in ADR-148; PR Factory budgets |
| Fan-out / council for research | Already: `/api/agents/council`, Agent Teams (ADR-172) |

Do **not**:

1. Run `curl …/install.sh | bash` on operator or VPS machines for LeadGen.
2. Register `@enderfga/claw-orchestrator` in `~/.openclaw/openclaw.json` for the LeadGen gateway.
3. Point 31 STAFF or OpenClaw Copilot at `session_start` / `council_start` / `ultraapp_*`.
4. Treat claw-orchestrator as a replacement for Owner OS, PR Factory, or buzzlock.
5. Route Claude subscription OAuth through non-native harnesses via this package.

## When to revisit

Only if **all** of these are true:

1. ADR-172 Agent Teams + worktrees proven useful on real disjoint tasks.
2. Owner explicitly wants OpenClaw to **dispatch** coding missions (AMBER package), not just observe.
3. A design exists that keeps Owner OS sole authority: clawo would be a **subprocess adapter
   behind** `EXTERNAL_AGENT_RUNNER`, with LeadGen path/risk policy applied *before* spawn —
   never raw 65-tool plugin into the gateway.
4. Eval still shows no cheaper extension of existing `claude_exec` / `cursor_exec`.

Until then: stay on ADR-172 + existing runners.

## Alternatives rejected

1. **“Natural fit → install plugin now”** — diagram similarity ≠ authority fit; 65-tool
   childProcess plugin would silently create a second dispatcher.
2. **Vendor as npm dep inside the monorepo** — Node island + dual dashboard + dual ledger.
3. **Replace `external_agents` with clawo sessions** — loses CAS leases, RED refuse-at-create,
   evidence-gated advance, OpenClaw GREEN-only Stage A contract.

## Consequences

- Docs: this ADR; pointer from ADR-172 / Agent Teams runbook.
- Memory: append ADR-173 in `memory/decisions.md`.
- Eval clone stays **outside** the product tree; not committed.
- No `AUTOMATION_FLAGS` change. No OpenClaw allowlist expansion. No deploy.

## Rollback

N/A for reject — nothing claw-orchestrator runtime shipped.
If an operator already installed the npm plugin locally: remove package path from
`~/.openclaw/openclaw.json`, `npm uninstall -g @enderfga/claw-orchestrator`, restart gateway.
