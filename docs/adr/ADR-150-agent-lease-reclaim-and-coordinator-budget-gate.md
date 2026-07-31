# ADR-150 — Agent-task lease reclaim + coordinator budget gate

**Date:** 2026-07-31
**Status:** Accepted (code-present, INERT — no flag flipped, not deployed)
**Branch:** `claude/agent-orchestration-integration-80ceed`
**Supersedes / relates:** ADR-148, ADR-149 (external agent orchestrator/runner); ADR-131 (skill registry)

## Context

The user asked to apply https://github.com/andyrewlee/awesome-agent-orchestrators to this
platform. That repository is a **curated link list of ~200 third-party orchestrators**, not a
library — there is nothing importable in it, and every entry orchestrates *coding agents*
(dev-time), which is a different plane from our revenue-bearing 31-agent runtime workforce.

We therefore mined it for *patterns* and checked each against our own code. Full mapping with
file:line evidence: `docs/superpowers/specs/2026-07-31-agent-orchestrator-gap-analysis-design.md`.

Coverage turned out near-total — worktree-isolated parallel agents, merge queue + ownership
conflict, swarm coordination, self-improving loops, scheduled task runners, budget/cost/
permission/checkpoint primitives and an owner assistant all already exist. Two mechanisms did
not.

## Decision

Port two patterns in-repo, additive and INERT by default. Vendor nothing.

### 1. `agent_task_queue.reap_stale_leases()` — terminal close-out of expired leases

`claim_next()` implements an atomic claim with optimistic locking, and `agent_runtime.py:730`
calls the result a lease. But `stale_tasks()` is **observe-only by design** ("Paperclip
philosophy: surface stuck tasks, don't auto-fix") and its only consumers are an Office HQ
snapshot and a badge count. A worker that dies between `claim_next()` and `complete()`/`fail()`
strands its task in `claimed`/`running` **forever** — no agent can ever pick it up, and the
work is silently dropped.

`reap_stale_leases()` marks the expired lease `failed` with
`lease_expired_after_N_attempts` and surfaces it for re-assignment. The transition re-asserts
the same optimistic-lock predicate as `claim_next` (`id` + `checkout_version` + current
status), so a reap cannot clobber a worker that finished legitimately mid-scan. Default is
`dry_run=True`. **No Alembic migration** — `checkout_version` (already bumped on every claim,
`claim_next:150`) is recorded in the reason for diagnostics.

**It is deliberately NOT a requeue**, and this was the design's one real hazard. The first
draft requeued to `pending` under an attempt cap, mirroring
`app/dev_control/reconcile.py:42-60`. That is unsafe *here*, for two reasons that
`reconcile.py` does not share:

- `complete()` (`:197-215`) and `fail()` (`:236-246`) filter on `id` + `status` only —
  **neither guards on `checkout_version`**. So a slow-but-alive worker whose lease was
  requeued keeps running; a second agent claims the same row; and the original's late
  `complete()` silently overwrites the second run. Bumping `checkout_version` on requeue does
  not fix this, precisely because those two writers ignore it.
- These leases wrap genuinely side-effecting work: `agent_runtime._durable_open`
  (`:717-736`) opens one for **every** runtime action, and `team_scheduler.py:309-333` opens
  one for **every** scheduled routine job. A double-run is therefore customer-visible, not
  queue hygiene.

Terminal-fail makes the safety property provable instead of assumed: once reaped the row is
`failed`, so `claim_next` will not offer it and the original worker's late
`complete()`/`fail()` no longer matches the claimed/running filter. Re-assignment stays a
human decision — which is also the more faithful reading of "surface, don't auto-fix".
Regression test: `test_a_reaped_task_cannot_be_reclaimed_or_overwritten`.

"Surface, don't auto-fix" **remains the default**: the reclaim is gated by
`AGENT_TASK_LEASE_REAP` (unset ⇒ INERT) and wired as scheduler job `task_lease_reap` at
hourly `:05` — an unoccupied slot. Registered in `AUTOMATION_FLAGS` and in
`automation_health`'s cadence map with a 3h grace, matching `meter_watch`/`social_drain`.

### 2. Coordinator consults the budget governor

`agent_budget.check()` enforces a per-agent daily token ceiling with soft-alert/hard-stop
tiers, but was called in exactly one place: `agents/staff.py:1436`. The coordinator's
`fan_out` / `coordinate_agentverse` / `debate` / `council` paths therefore issued one LLM call
per agent per round with **no daily ceiling** — `_llm_rate_ok()` (`coordinator.py:182`) caps
burst-per-minute, not the day's total.

On a free-provider-only stack this is a real risk, not a theoretical one: a known landmine is
*"Groq TPD content-heavy days pe khatam"* (CLAUDE.md §7). A runaway swarm can exhaust the
day's free quota and degrade the **voice path**, which is revenue-bearing.

`_run_agent` now consults `agent_budget.check(agent)` on the **draft/LLM branch only** and
returns `mode="skipped"` instead of calling the LLM when the agent is over budget. The
`execute` tool branch is untouched — it already ran under `staff`'s governance and
double-gating it would change side-effecting behaviour. The check is wrapped in the module's
defensive `try/except` and **fails OPEN**, consistent with §5's fail-open rule for meters.

This is INERT by construction: `check()` short-circuits to `allowed=True` while
`AGENT_BUDGET_ENABLED` is off, which is the default. No flag was flipped.

## Rejected

- **Vendoring any listed tool** (gastown, ralph-*, paperclip, skillfold, …) — free-stack
  mandate, supply-chain risk, none speak our stack.
- **A skill lockfile** (skillfold) — dev-time only, zero runtime or revenue effect. (Not
  because ADR-131 covers it: ADR-131 pins *our own* skills via git, whereas skillfold pins
  *third-party* skill revisions. Different problem, still not one we have.)
- **Another cockpit/kanban/TUI surface** — contradicts the ops-cockpit IA decision; we already
  have `/app/automation`, `/app/office`, `/app/control-center`.
- **Any flag flip, commit, push or deploy** — WS-1 is explicitly "out of scope: flag flips";
  CLAUDE.md §8 requires the user to ask.

## Consequences

- Nothing changes in production until the owner sets `AGENT_TASK_LEASE_REAP=1` (and,
  separately, `AGENT_BUDGET_ENABLED=1` for the budget gate to bite).
- When armed, a dead worker's task is resolved as `failed` with a stated reason instead of
  sitting in `claimed` forever, so the Office HQ stuck-count becomes an actionable work list
  rather than a monotonically growing number. It does **not** auto-retry; re-assignment is
  the owner's call.
- **Precondition before arming `AGENT_BUDGET_ENABLED=1`:** `agent_budget.check()` is sync and
  reaches Redis via `_get_today_usage` → `agent_cost_tracker.agent_today`
  (`agent_budget.py:98-102`). `coordinator.fan_out` runs N agents concurrently, so once the
  flag is live that becomes N blocking calls inside the event loop per swarm. Today it
  short-circuits at `agent_budget.py:117` before touching Redis, so it is free while INERT.
  Arming it should come with the `asyncio.to_thread` + deadline treatment CLAUDE.md §4
  requires for exactly this shape. (`staff.py:1436` calls it the same sync way — the fix
  belongs at the `check()` boundary, for both callers, not in the coordinator alone.)
- No migration, no new routes, no customer mutation, no sends. Compliance gates untouched;
  calling stays HARD OFF.

## Evidence

- `pytest tests/test_agent_task_lease_reap.py tests/test_coordinator_budget_gate.py -q` → **12 passed**
- Related regression (coordinator + harness-coordinator + 6 scheduler + 2 automation_health +
  office_hq + sales_autopilot_scheduler) → **242 passed, 13 weekday-skips, 0 failed**
- `scripts/prod_check.py` → `ALL CHECKS PASSED`, 1216 routes, automation 0 gaps
- `scripts/check_secrets.py` → `no secrets detected`
- `ruff check` on all 7 touched files → clean
- `git diff --stat` → 5 files, **132 insertions, 0 deletions**, no route decorators added
