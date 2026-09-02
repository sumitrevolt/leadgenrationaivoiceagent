# Coordination plane

How Cursor, Claude Code, OpenCode and Monkey Code share this repo without
overwriting each other, and how repo work connects to the 31 runtime STAFF agents.

## Planes

```
#build        coding tools working this checkout      (Cursor/Claude/OpenCode/Monkey)
#dev          reviewed changes, PRs, test results
#admin        Boss routing + owner decisions
#staff-pulse  the 31 runtime STAFF, read-only mirror
```

Control flows one way only:

```
Buzz (#admin) -> Boss -> Owner OS / OpenClaw -> 31 runtime STAFF -> Celery
```

Buzz is an interface, never a second control plane. A coding tool never issues a
command to a runtime STAFF agent — it raises the need in `#dev` and Boss routes it.

## File locks — use `buzzlock`

`LOCKS.json` is the registry; `scripts/buzzlock.py` is how you touch it. Do not
hand-edit the JSON — the CLI writes it atomically and posts the matching `#build`
line in the same step.

```bash
python scripts/buzzlock.py status
python scripts/buzzlock.py claim app/api/growth_revenue.py --tool CLAUDE --reason "ADR-159 canary"
# ... work ...
python scripts/buzzlock.py release app/api/growth_revenue.py --tool CLAUDE --evidence "3 tests green, exit 0"
python scripts/buzzlock.py handoff --tool CURSOR --next CLAUDE --goal "..." --done "..." --evidence "exit 0" --left "..." --touched "..."
```

`--tool` is one of `CURSOR` `CLAUDE` `CODEX` `GOOSE` `OPENCODE` `FREEBUFF` `MONKEY`.

A `handoff` with a blank Evidence line is refused (exit 1) — that post would be a rumour.

A tool missing from that list cannot claim, so it edits the tree with no lock at
all — which is the failure the registry exists to prevent. Add new harnesses to
`TOOLS` in `scripts/buzzlock.py` *before* pointing them at this checkout.

`LOCKS.json` is gitignored and per-checkout; `buzzlock` creates it on first use.
(Until 2026-08-09 a fresh worktree raised `FileNotFoundError` on `status`, so the
protocol was quietly skipped on every new tree.)

**Exit codes matter:** `0` ok · `1` usage error · `2` refused. A `2` on claim means
another tool holds the file — stop and pick different work. The CLI posts your
`BLOCKED ON` line automatically when it refuses.

Claims older than `stale_after_minutes` (default 240) can be taken over:

```bash
python scripts/buzzlock.py break app/api/growth_revenue.py --tool CURSOR
```

`break` refuses with exit 2 if the claim is still fresh.

Buzz posting is best-effort — if the Buzz CLI or owner credential is missing the
lock still applies and the command still succeeds. The JSON is the contract; chat is
the mirror.

## Staff pulse

`scripts/buzz_staff_pulse.py` posts the 31/31 STAFF digest into `#staff-pulse`.
It reads `team_status()` from the live app container over SSH — read-only, no
writes, no deploy. Runs hourly via the Windows scheduled task
**"LeadGen Buzz Staff Pulse"**; `--dry-run` prints without posting.

It flags an agent `warn` when it has been silent over 24h and `fail` on errors or an
offline state — the stale case is the one that otherwise goes unnoticed.

## Claude Code Agent Teams (coding plane)

Native Claude Code multi-session coordination (ADR-172). Opt-in via
`.claude/settings.json` → `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. Canary: **2 teammates**,
worktrees `agent/tm{N}/<slug>`, frozen paths from **SSOT**
`docs/coordination/canary_frozen_paths.yml` (loader `scripts/canary_frozen.py` — never paste
twins). Lead prompt: `docs/coordination/CANARY_LEAD_PROMPT.md`.

Runbook: `docs/runbooks/CLAUDE_AGENT_TEAMS.md`. claw-orchestrator: REJECT vendor (ADR-173).


## Hard rules (all tools)

- Read before Edit — never edit off stale content.
- Context-grep callers / routes / tests before changing anything.
- Never `git add -A`. Stage explicit paths only.
- No commit / push / deploy unless the owner asks. Deploy is
  `scripts/deploy_vps.sh` with `APP_VERSION=<sha>`.
- Duplicate-route grep across all split routers — FastAPI is first-route-wins.
- Evidence beats prose: exit code, or it did not happen.
- Secrets never in a message, commit, or lock reason.
- Swara / voice path is FROZEN — propose, do not edit.
- Compliance gates (DND, TRAI window, consent, DPDP) are RED. Weakening one is an
  abort, not a fix.
- Parallel Claude teammates = worktree isolation mandatory (ADR-172).

## Related

- Autonomy tiers and the single human gate: `~/.buzz/GUIDES/AUTONOMY_POLICY.md`
- Canonical 31-agent routing: `~/.buzz/GUIDES/STAFF_ROUTING_MAP.md`
- Coding-agent protocol in full: `~/.buzz/GUIDES/CODING_AGENT_PROTOCOL.md`
- Buzz operating model: `~/.buzz/GUIDES/BUZZ_OPERATING_MODEL.md`
- Claude Agent Teams runbook: `docs/runbooks/CLAUDE_AGENT_TEAMS.md`
- ADR-172: `docs/adr/ADR-172-claude-agent-teams-worktrees.md`
