# AI-Firstify Assessment Report

**Project:** LeadGen AI Platform (leadsgenai.in)
**Date:** 2026-07-18
**Mode:** Re-engineer (audit + safe active fixes)
**Focus:** All 7 dimensions · Skills & agents architecture · Context hygiene

> **Rubric calibration:** The stock ai-firstify rubric targets *personal AI-first tools* — it scores LLM API calls, databases, and frontends as RED. LeadGen AI is a legitimate production SaaS where those ARE the product (AI voice telecaller + AI marketing automation). This report therefore assesses the **AI-agent development / operations layer** — how the codebase is built and driven by Claude Code (CLAUDE.md, memory, skills, sub-agents, graphify, safety gates, workflows) — NOT whether the product is "allowed" to use AI. Where a dimension is judged in this adapted sense, it is noted.

## Overall Score

| Dimension | Score | Summary |
|-----------|-------|---------|
| 1. Project Structure | 🟡 YELLOW | Excellent CLAUDE.md/memory/git; but 128 root files + chronically dirty worktree |
| 2. Agent Architecture | 🟢 GREEN | Product LLM use is legitimate + well-guarded; dev workflow is Claude-Code-native |
| 3. Skill Usage | 🟢 GREEN | 124 skills + `.claude/{agents,commands,skills}` + MCP + slash commands |
| 4. Scope & Complexity | 🟡 YELLOW | Real SaaS breadth (700+ routes, ~40 containers); some dormant/local-only features |
| 5. Context Hygiene | 🟡 YELLOW | Lean 126-line CLAUDE.md + progressive disclosure; undermined by ~97 temp scripts |
| 6. Safety | 🟢 GREEN | Strong compliance invariants, secrets-in-.env discipline, human-in-loop gates |
| 7. Workflow Design | 🟢 GREEN | Prescriptive skills, slash commands, Loop mode, validation scripts, DoD |

**Verdict:** A **mature, genuinely AI-first codebase** for its development/agent-ops layer — well above the typical repo. The single cross-cutting weakness is **working-tree / context pollution** (temp-script sprawl + chronically dirty tree), which is fixable and has already caused real deploy incidents.

## Priority Recommendations

1. **[HIGH] Kill temp-script / worktree pollution.** ~97 `scripts/_tmp_*` + `_canary_*` scripts, 18 root temp artifacts (`*_exit.txt`, `pytest_*.txt`, `forensics_*.txt`, `upi_flip_result.txt`), and `*.bak.*` files sit untracked, polluting `git status` and agent context. *(Effort: S — `.gitignore` patterns applied this session; one-time sweep to `scripts/_debug/` still needed.)*
2. **[HIGH] Resolve the dirty parallel-agent worktree.** 15 modified tracked files (app/api/*, frontend/*, CLAUDE.md, memory/*, tests/*) are uncommitted WIP from parallel Cursor/Codex agents. The "chronically dirty tree" is a named landmine that has caused deploy foot-guns. Owner should commit/stash per-owner. *(Effort: M — human decision.)*
3. **[MEDIUM] De-clutter repo root (128 files).** Move loose root artifacts (`tmux*`, `check_jiya.py`, `*_result.txt`, `forensics_*.txt`) into `docs/`, `scripts/_debug/`, or `scratch/`. *(Effort: S.)*
4. **[MEDIUM] Confirm zero committed secrets.** `git ls-files | grep -i .env` could not complete this session (git timeouts on the large tree). Run `scripts/check_secrets.py` / `/verify` to positively confirm. *(Effort: S.)*
5. **[LOW] Index the docs/ ADR sprawl.** `docs/` holds dozens of ADRs/runbooks; add a `docs/INDEX.md` or `docs/adr/archive/` so the current ones stay findable. *(Effort: S.)*

## Detailed Findings

### Dimension 1: Project Structure — 🟡 YELLOW
- **Strong:** `CLAUDE.md` = 126 lines (rubric GREEN threshold is <200; excellent). `AGENTS.md` byte-synced (126 lines) per the repo's own rule. `.gitignore` present and thorough (secrets, venv, worktrees, build artifacts). Git active with frequent commits + PR merges. `memory/`, `docs/`, `app/`, `frontend/`, `scripts/` logically organized.
- **Weak:** 128 files in repo root (rubric flags 50+); "tree chronically dirty" is explicitly documented as a landmine. Temp/debug artifacts leak into root and `scripts/`.

### Dimension 2: Agent Architecture — 🟢 GREEN (adapted)
- Product LLM use (Mistral/Groq/Gemini/etc. via `app/voice_agent/free_ai.py`) is the core product, with an escalating 429 circuit-breaker and free-provider-only mandate — this is legitimate, well-engineered application architecture, not an "embedded agent" anti-pattern.
- The **development** workflow is Claude-Code-native: sub-agents (`.claude/agents/`), skills, `.mcp.json` (graphify + gated `/mcp`). No rogue custom dev-agent framework. Loop Engineer mode formalizes the inspect→implement→verify loop.

### Dimension 3: Skill Usage — 🟢 GREEN
- 124 `SKILL.md` under `.claude/skills/` (plus plugin skills; CLAUDE.md cites ~250 in the skill pack). `.claude/` has `agents/`, `commands/`, `skills/`.
- Prescriptive slash commands: `/verify`, `/ship`, `/checkpoint`, `/learn`, `/compact-check`, `/optimize`, `/test-expand`.
- Progressive disclosure in place; graphify graph (`app/graphify-out/graph.json`) as a token-saving navigation layer wired via `.mcp.json`.

### Dimension 4: Scope & Complexity — 🟡 YELLOW
- Genuinely large product: ~700 routes, 4 dashboards, ~40 containers (app, workers, Postgres/PgBouncer, Redis×2, Qdrant, FreeSWITCH, Postiz, Temporal, full obs stack). Justified for a real SaaS with paying customers.
- Watch items: dormant/local-only features (Unity WebGL — local-only, gated off), a staging stack running alongside prod, and env-flag-gated features that risk accumulating. Not RED (it's a real business), but complexity is high and warrants periodic pruning of truly-dead paths.

### Dimension 5: Context Hygiene — 🟡 YELLOW
- **Strong:** CLAUDE.md is lean (126 lines) with explicit token-discipline; deep knowledge offloaded to `memory/` (INDEX, decisions, incidents, playbooks, glossary, integrations, backlog), dated history to `docs/SESSION_LOG.md`, and a `## Current State` hot-cache capped at ~40 lines. Graphify enables graph-first retrieval instead of re-reading the repo. This is textbook progressive disclosure.
- **Weak:** the ~97 `_tmp_*`/`_canary_*` scripts + root temp artifacts pollute `git status` and any agent that scans the tree — the exact opposite of the disciplined CLAUDE.md. Fixing the pollution (rec #1) moves this to GREEN.

### Dimension 6: Safety — 🟢 GREEN
- Compliance invariants are explicit and fail-safe: DND scrub **fail-closed**, DPDP data-minimization + 90-day retention + purge API, billing truth single-sourced with contract test, `platform_dial` HARD-OFF (3-layer kill), WhatsApp auto-send OFF (1-click human-in-loop only), foreign-trunk block.
- Secrets discipline: "secrets only in `.env` (gitignored)"; `.gitignore` carries 8 secret/key patterns + `.env*` with example negations; a `check_secrets.py` gate + `sk_` proxy-only rule.
- *Caveat:* a positive "no `.env` tracked in git" check couldn't be run this session (git timeouts) — run `scripts/check_secrets.py` to confirm (rec #4).

### Dimension 7: Workflow Design — 🟢 GREEN
- Prescriptive, step-by-step skills + slash commands; Loop Engineer mode with an 8-hat review gate and a canonical 9-field output format.
- Feedback loops: `prod_check.py`, `check_secrets.py`, `run_tests.bat`, contract tests (billing-truth), `agent_tester.py` voice scorecard; deploy via a self-verifying `deploy_vps.sh` (SHA/skew/smoke gates).
- Git discipline documented in §8 (no `git add -A`, no commit/push without ask, small diffs, plan-before-multifile).

## Changes Made (this session)

| Action | File | Description |
|--------|------|-------------|
| Modified | `.gitignore` | Added ignore patterns for `scripts/_tmp_*`, `scripts/_canary_*`, `*_exit.txt`, `pytest_*.txt`, `*_result.txt`, `forensics_*.txt`, `*.bak`, `*.bak.*` — stops temp-artifact pollution of git status / agent context |
| Created | `docs/archive/2026-07/AI_FIRSTIFY_REPORT_2026-07-18.md` | This report |

*Only additive, non-colliding changes were applied. `.gitignore` is not part of the current parallel-agent WIP, so this edit does not risk clobbering in-progress work. No commit was made (per repo §8 — owner reviews/commits). No structural refactor, no file deletion, no touching of modified-in-WIP files.*

## Still Needs Human Decision

- [ ] The 15 modified tracked files (parallel Cursor/Codex WIP) — commit, stash, or discard per the owning agent/session, so the tree can go clean.
- [ ] The ~97 `_tmp_*`/`_canary_*` scripts + 18 root temp files — bulk-delete or sweep into `scripts/_debug/` (now git-ignored) / a `scratch/` dir. (Kept on disk this session; not deleted, since parallel work may reference them.)
- [ ] Whether to archive old ADRs under `docs/adr/archive/` and add `docs/INDEX.md`.
- [ ] Whether to remove truly-dead feature paths (e.g. local-only Unity WebGL) from the tree vs. leaving gated-off.

## Recommended Next Steps

1. On a clean-tree session, run `git status` and confirm the new `.gitignore` patterns removed the temp noise; then sweep any remaining loose temp scripts into `scripts/_debug/`.
2. Resolve the parallel-agent WIP (commit/stash), then de-clutter root (rec #3).
3. Run `scripts/check_secrets.py` (or `/verify`) to positively confirm no committed secrets.
4. Add `docs/INDEX.md` and consider `docs/adr/archive/` for ADR sprawl.
