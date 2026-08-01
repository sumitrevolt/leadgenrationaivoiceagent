# awesome-agent-orchestrators → LeadGen AI: gap analysis + design

**Date:** 2026-07-31
**Source:** https://github.com/andyrewlee/awesome-agent-orchestrators
**Branch/worktree:** `claude/agent-orchestration-integration-80ceed`

---

## 0. What the source repo actually is

It is a **curated link list**, not a library. There is no code to "apply" — the repository
contains a single `README.md` cataloguing ~200 third-party orchestrators across 8 categories.
Nothing in it is importable, and nothing in it is a dependency we could adopt.

Two consequences drive this whole document:

1. **The only honest way to "apply" it is to mine the *patterns* and check each one against
   our own code**, then build the thin set that is genuinely missing. Vendoring third-party
   Go/Node/Rust binaries into a live revenue platform is rejected outright: it violates the
   free-stack mandate, adds supply-chain risk, and none of them speak our stack.
2. **Every entry orchestrates *coding agents* (dev-time).** Parallel Claude/Codex sessions,
   git worktrees, GitHub-Action runners, issue-tracker pullers. Our revenue-bearing
   orchestration is a *different plane* — the 31-agent runtime workforce. The list has
   essentially nothing to say about revenue; see §4.

**Sections reviewed:** all 8 — Parallel Coding Agents (Terminal), Parallel Coding Agents
(Desktop & Web), Multi-Agent Swarms, Autonomous Loop Runners, Autonomous Task Runners,
Agent Infrastructure & Primitives, Personal Assistants, Resting. Fetched 2026-07-31.

---

## 1. Category → in-house counterpart (with evidence)

| List category | Our counterpart | Verdict |
|---|---|---|
| Parallel Coding Agents (Terminal + Desktop/Web) | `app/dev_control/external_agents/` — `runner/worktrees.py`, `runner/claude_exec.py`, `runner/cursor_exec.py`, `runner/review_parse.py`, `runner/status.py`, `runner/lease_contract.py`, `cas.py` (5096 LOC) | **PRESENT** |
| Multi-Agent Swarms | `app/agents/coordinator.py:344` `coordinate`, `:407` `fan_out`, `:662` `debate`, `:770` `coordinate_hierarchical`, `:928` `coordinate_agentverse`, `:1083` `council`; `staff_supervisor.py`, `supervisor.py`, `sales_team.py`, `agent_registry.py` | **PRESENT** |
| Autonomous Loop Runners | `app/agents/self_improve.py` (1748 LOC, self-requeue + dead-man revive), `external_agents/runner/loop.py`, `voice_agent/voice_self_improve.py` | **PRESENT** |
| Autonomous Task Runners | `app/platform/team_scheduler.py` (1641 LOC, ~24 jobs), `agent_task_queue.py`, `process_autostart.py`, `api/dev_tasks.py` | **PRESENT** |
| Agent Infrastructure & Primitives | `agent_runtime*.py` (+ cancellation/idempotency/pilots/workforce), `agent_budget.py`, `agent_cost_tracker.py`, `agents/cred_pool.py`, `agents/harness/` (contracts/enforce/sandbox/stop/audit), `batch_harness.py`, `approvals_bridge.py`, `dlq_retry.py`, `job_time_budget.py`, `agent_permissions.py`, `agent_checkpoints.py`, `trajectory.py` | **PRESENT** |
| Personal Assistants | `app/platform/owner_os.py`, `app/integrations/openclaw/`, `boss_council.py`, `office_hq.py` | **PRESENT** |

Coverage is near-total. This matches the standing project finding
(`memory/platform-feature-complete`): *ship dormant-but-wireable gaps, don't fabricate.*
The expected output of this exercise was 3–6 thin real gaps — not twenty new features.

### Discriminating checks (mechanism-level, not concept-level)

| Pattern (source) | Mechanism grepped | Result |
|---|---|---|
| Merge queue + conflict handling (gastown, Aperant) | `external_agents/schema.py:33` `MERGE_QUEUED`, `policy.py:240` `ownership_conflict`, `orchestrator.py:164` `path_lock_conflict` | present |
| Independent verifier per result (kodo) | `coordinator.py:538` `_verify`, `agents/eval_gate.py`, `agents/agent_consensus.py` | present |
| Quota-aware harness rotation (Claudexor) | `voice_agent/free_ai.py` provider chain + 429 circuit breaker; `agents/cred_pool.py`; 9-key Gemini pool | present |
| Zero-LLM-in-loop routing (bernstein) | `coordinator.py:281-286` deterministic keyword fallback when the LLM returns nothing; `:182` `_llm_rate_ok` per-minute cap | present (as fallback) |
| Spend cap + rollback (MartinLoop) | `agent_budget.check()` — called at `agents/staff.py:1436` **only** | **GAP — see §2.B** |
| Heartbeat + claim expiry + reclaim (paperclip, swarm-protocol) | `agent_task_queue.py:412` `stale_tasks()` — surfaces only | **GAP — see §2.A** |
| Skill lockfile w/ pinned revisions (skillfold) | no lock artifact under `.claude/skills` | considered, **rejected** — dev-time only, zero runtime/revenue effect, and ADR-131 already made `.claude/skills` the single canonical tracked root under git, which pins revisions by commit |
| Context wipe / fresh session per task (neuralyzer, ralphex) | `agents/trajectory.py`, `agent_checkpoints.py`, `self_improve` fresh-tick chain | present |

---

## 2. The two real gaps

### A. Agent task leases are surfaced but never reclaimed

`agent_task_queue.py` implements an atomic claim with optimistic locking
(`claim_next`, `:117-172`) and `agent_runtime.py:730` documents the result as
*"claim → running (lease semantics; stale_tasks() surfaces expired leases)"*.

But `stale_tasks()` (`:412`) is **observe-only** — by explicit design, its docstring reads
*"Paperclip philosophy: surface stuck tasks, don't auto-fix."* Its only consumers are the
Office HQ snapshot (`office_hq.py:2274`) and a badge count (`:1540`). **Nothing anywhere
requeues or fails an expired lease.**

Failure mode: a worker that dies between `claim_next` and `complete`/`fail` leaves its task
in `claimed`/`running` **forever**. It never returns to `pending`, so no other agent can pick
it up; the work is silently dropped and the queue's stuck-count grows without bound. The
in-repo precedent for the fix already exists one directory over —
`app/dev_control/reconcile.py:42-60` requeues stalled dev-control missions under a retry cap.

**Design.** Add `reap_stale_leases()` to `agent_task_queue.py`:

- Selects the same rows `stale_tasks()` does (`claimed`/`running`, `claimed_at` older than the
  threshold), bounded by an explicit `limit`.
- Transitions each to `failed` with a `lease_expired_after_N_attempts` summary and surfaces it
  for re-assignment.
- Uses the same optimistic-lock guard as `claim_next` (match on `id` + `checkout_version` +
  current status) so a reap can never race a live worker that is finishing legitimately.
- **No Alembic migration** — `checkout_version` (already incremented per claim at
  `claim_next:150`) is recorded in the reason for diagnostics.
- `dry_run=True` is the default of the function itself: it reports what it *would* do and
  mutates nothing.

**Rejected mid-design: requeue-to-`pending`.** The first draft mirrored
`dev_control/reconcile.py:42-60` — requeue under an attempt cap, terminal-fail at the cap.
Two facts, both verified in source, make that unsafe *here* in a way it isn't for
`reconcile.py`:

1. `complete()` (`:197-215`) and `fail()` (`:236-246`) filter on `id` + `status` only —
   **neither guards on `checkout_version`.** A slow-but-alive worker whose lease was requeued
   keeps running, a second agent claims the same row, and the original's late `complete()`
   silently overwrites the second run. Bumping `checkout_version` on requeue does not help,
   precisely because those two writers ignore it.
2. These leases wrap side-effecting work: `agent_runtime._durable_open` (`:717-736`) opens one
   for **every** runtime action; `team_scheduler.py:309-333` opens one for **every** scheduled
   routine job. So a double-run is customer-visible, not queue hygiene.

Terminal-fail makes the property provable rather than merely bounded: once reaped the row is
`failed`, `claim_next` will not offer it, and the original worker's late `complete()` no
longer matches the claimed/running filter. Re-assignment stays a human decision — the more
faithful reading of "surface, don't auto-fix". Covered by
`test_a_reaped_task_cannot_be_reclaimed_or_overwritten`.

**Respecting the existing philosophy.** "Surface, don't auto-fix" stays the default.
The reaper is gated by `AGENT_TASK_LEASE_REAP` (unset ⇒ INERT), and the scheduler job
no-ops when the flag is off. Enabling it is a separate, explicit owner decision.

**Wiring.** New scheduler job `task_lease_reap`, hourly at `:05` — a slot no existing job
occupies (`:05` ops, `:10` social_drain, `:20` reply_triage/product_one_health, `:25`
sales_autopilot, `:35` watchdog, `:40` approval_email_sweep/mcp_engineer, `:45` engineer_sre,
`:50` onboard, `:55` meter_watch). Registered in `AUTOMATION_FLAGS` and in
`automation_health.py`'s cadence map with a 3h grace, matching `meter_watch`.

### B. The coordinator's swarm paths bypass the budget governor

`agent_budget.check()` enforces a per-agent daily token ceiling with a 3-tier
soft-alert/hard-stop response (`agent_budget.py:107-163`). It is called in exactly one place:
`agents/staff.py:1436`, before `run_member`.

The coordinator does not call it. So `fan_out` (`:407`, N agents concurrently),
`coordinate_agentverse` (`:928`, recruits experts then iterates), `debate` (`:662`, multi-round)
and `council` (`:1083`) each issue LLM calls per agent per round with **no spend ceiling**.
The only brake is `_llm_rate_ok()` (`:182`), which is a *rate* limit (calls/minute), not a
*budget* — it caps burst, not daily total.

Why this matters concretely on our stack: providers are free-tier, and a known landmine is
*"Groq TPD content-heavy days pe khatam"* (CLAUDE.md §7). A runaway swarm can exhaust the
day's free quota and starve the **voice agent** — which is revenue-bearing. Unbounded
dev-time orchestration degrading a paying customer's phone calls is the actual risk.

**Design.** In `coordinator._run_agent` (`:289`), before the LLM branch, consult
`agent_budget.check(agent)`. If `allowed` is false, skip that agent and return a
`mode="skipped"` result carrying the budget verdict, instead of calling the LLM.

- Placed on the **draft/LLM branch only** — the `execute` tool branch (`:291-324`) already
  ran its side-effecting work under `staff`'s own governance and must not change behaviour.
- Already INERT by construction: `check()` short-circuits to `allowed=True` when
  `AGENT_BUDGET_ENABLED` is off (`agent_budget.py:117-122`), which is the default. So this
  is a no-op until the owner arms budgets — no flag flip performed here.
- Wrapped in the module's defensive `try/except` idiom: a budget-subsystem failure must
  fail **open** (agent runs), consistent with §5's fail-open rule for meters.

---

## 3. Non-goals (explicitly rejected)

- **Vendoring any listed tool.** Free-stack mandate + supply chain. Patterns only, in-repo.
- **New dashboards / TUIs / kanban surfaces.** We already have `/app/automation`,
  `/app/office`, `/app/control-center`. Adding another cockpit contradicts
  `memory/ops-cockpit-ia-decision`.
- **Flag flips.** WS-1 is explicit: *out of scope: flag flips*. Everything here ships INERT.
- **Commit / push / deploy.** Not performed; requires the user to ask (CLAUDE.md §8).
- **Touching compliance gates.** DND/DLT/consent/retention untouched. Calling stays HARD OFF.

---

## 4. On "launch-ready and revenue-ready"

This cannot be delivered from this session, and the source repo is not the lever.

Per `docs/context/CURRENT_STATE.md` §"Top next actions" and `ACTIVE_WORK.md` WS-2/WS-3, the
three things standing between the platform and its 2nd paying customer are **owner actions**,
not code:

1. Owner login → enable `VIDEO_CUSTOMER_REVIEW_ENABLED=1` +
   `VIDEO_CUSTOMER_REVIEW_CLIENTS=jiya-makeover`, then run the authenticated read-only Jiya
   Preview canary.
2. Owner inbox canary send + the Estique 1-click decision (WS-2).
3. GTM Hot Queue `/app/inbox` worked to a 2nd Marketing customer.

None of these is unblocked by an orchestration change, and a curated list of *coding-agent*
orchestrators speaks to none of them. Claiming otherwise would be exactly the causal error
CLAUDE.md §7 warns about. What §2 delivers is **reliability of the automation that already
exists** — a dropped agent task no longer vanishes silently, and a swarm can no longer eat the
free-tier quota that the revenue-bearing voice path depends on.

---

## 5. Verification plan

- New pytest module `tests/test_agent_task_lease_reap.py` (real in-memory sqlite session, not
  a mock, so the optimistic-lock UPDATE is actually exercised): dry-run mutates nothing;
  expired lease closes terminally and is NOT requeued; a reaped task can neither be re-claimed
  nor overwritten by its original worker's late `complete()`; fresh/done/pending rows are left
  alone; `limit` bounds the scan; DB failure never raises; flag INERT by default.
- New pytest module `tests/test_coordinator_budget_gate.py`: budget-disabled path is a
  behavioural no-op; blocked agent skips the LLM; budget-subsystem exception fails open.
- `scripts/prod_check.py`, `scripts/check_secrets.py`, duplicate-route grep (no new routes
  added, so the grep is a confirmation not a risk).
