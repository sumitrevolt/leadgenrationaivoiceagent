# Workflow Improvement Backlog — Infra + Agents (2026-06-28)

> **Context:** "Claude workflow for infrastructure + agents workflow improvement" sprint. Measure-first (2 skeptical discovery agents, evidence-backed) on a mature, production-GREEN platform. Shipped the **low-risk, high-value** wins this session; deferred the **M-risk** items here with rationale (they touch live revenue/agent hot-paths → deserve their own careful change).

## ✅ Shipped this session (additive, tested, flag-safe)

| Layer | Change | File | Risk |
|---|---|---|---|
| **Claude tooling** | `infra-doctor` sub-agent (read-only VPS/Docker/deploy diagnostician) | `.claude/agents/infra-doctor/AGENT.md` | S (md only) |
| **Claude tooling** | `agent-workflow-auditor` sub-agent (read-only agent-loop auditor) | `.claude/agents/agent-workflow-auditor/AGENT.md` | S (md only) |
| **Platform INFRA** | `validate_env.py` deploy-safety check (revenue-path env readiness; prod secret gap = exit 1, ops config = WARN) | `scripts/validate_env.py` | S (CLI, not in request path) |
| **Agent workflows** | `team.stats()` per-agent success-rate + last-run rollup + `/api/platform/team/stats` | `app/platform/team.py`, `app/api/team.py` | S (observability-only) |
| **Agent workflows** | DLQ `MAX_ATTEMPTS` 2→3 + counts TTL 6h→12h (transient 429/500/timeout recovery) | `app/platform/dlq_retry.py` | L (only affects already-failed jobs) |

Tests: `tests/test_team_stats.py` (aggregation + graceful) · `validate_env.py` PASS. prod_check green.

### Suggested next step (Claude tooling)
- Wire `team.stats()` into a `/app/team` or `/app/automation` widget (per-agent success-rate badge) so the operator SEES degrade without curling the API. (UI-only, additive.)
- Add `python scripts/validate_env.py` as step-0 in the deploy loop (`ship-checklist` / `leadgen-ops`).

---

## ✅ Deferred items — RESOLVED 2026-06-28 ("sab karo kuch mat chodo")

**Outcome:** D1/D2/D3 shipped (each flag-gated INERT-by-default + tested). **D4 & D5 = FALSE POSITIVES** — measure-first caught them (don't re-flag):
- **D4 (flow-revive):** flow runs go through `app/agents/flow_dispatch.start()` which routes linear→`process_engine` / dag→`dag_engine` + enqueues `process_tick`. BOTH engines' `ensure_alive()` are already in the watchdog (`team_scheduler.py:597,603`). Flows ARE covered. Agent even named the wrong module dir. **No fix — already handled.**
- **D5 (restore-drill cron):** VERIFIED present on VPS crontab (`0 3 1 * * /opt/leadgen/scripts/pg_restore_drill.sh`), alongside nightly backup + pg_backup + offsite-mail + obsidian push. **No fix — already wired.**

Shipped (gated, tested in `tests/test_workflow_guards.py`):
- **D1** eval_gate→self_improve (`EVAL_GATE` / `EVAL_GATE_HARD`, observe-only then soft de-prioritize) — `app/agents/self_improve.py`
- **D2** coordinator LLM rate-cap (`COORDINATOR_LLM_CAP_PER_MIN`, fail-open) — `app/agents/coordinator.py`
- **D3** DLQ retry-storm guard (`QUEUE_DEPTH_BACKPRESSURE`/`QUEUE_DEPTH_CAP`, defers sweep on flooded queue, no job loss) — `app/platform/dlq_retry.py`

Flags registered: `app/api/automation_flags.py` + `.env.example`. Broader API/scheduler-level submission backpressure (reject NEW tasks) remains the only un-done piece — genuinely M-risk hot-path, needs a load-test; left here intentionally.

---

## Original deferred detail (rationale, historical)

### D1 — `eval_gate` wired into self_improve loop  *(agent workflows)*
- **Evidence:** `app/agents/eval_gate.py` exists (regression-detection) but `app/agents/self_improve.py` computes `outcome_value` deterministically and never calls `eval_gate.score_and_gate(...)`. The 2026-06-16 audit (eval_gate docstring) flagged this.
- **Why deferred:** modifies the live forever-loop's skip/accept logic. `EVAL_GATE` flag is INERT by default so wiring is *behaviorally safe*, but needs careful signature check + a loop-behavior test before shipping. Value: catches slow quality drift (0.85→0.62) that the deterministic value misses.
- **Risk:** M · flag-gated (`EVAL_GATE`).

### D2 — coordinator LLM cost cap  *(agent workflows)*
- **Evidence:** `app/agents/coordinator.py` (`plan/coordinate/fan_out/reflect`) calls `free_ai.chat` with NO cost tracking; `self_improve` has `SELFIMPROVE_COST_CAP`. If coordinator runs in a recurring/public path, cost is unbounded.
- **Fix:** mirror self_improve's cost-tracker, or a `max_llm_calls` guard (e.g. ≤4 calls/invocation, fail-open). New flag `COORDINATOR_COST_CAP`.
- **Risk:** M (governance; changes coordinator behavior under cap).

### D3 — Redis OOM / queue backpressure  *(infra)*
- **Evidence:** `docker-compose.vps.yml` Redis `--maxmemory-policy noeviction` (broker+locks+idempotency share it); `alert_rules.yml` detects at >100 tasks but no *pre-enqueue* guard. Burst (onboard 100 clients) can flood before alert.
- **Fix:** pre-submit guard — reject (`503`) if `redis used_memory > 90%` or `llen celery > threshold`. New flags `REDIS_BACKPRESSURE` / `QUEUE_DEPTH_BACKPRESSURE`.
- **Why deferred:** touches the task-submission hot-path on a live revenue platform — needs load-test + careful fail-mode (fail-loud vs fail-open) decision. Alerting already exists, so not urgent.
- **Risk:** M.

### D4 — flow-layer stale-revive  *(agent workflows)*
- **Evidence:** `app/automation/flow_triggers.py` runs every 5 min but `flow_dispatch` has no `ensure_alive()` in the watchdog (process/DAG engines do). A stuck RUNNING flow won't auto-recover.
- **Fix:** watchdog checks `list_runs()` for stale RUNNING flows → trigger `process_tick`.
- **Risk:** L (defensive; engines already protected).

### D5 — restore-drill cron confirm  *(infra ops)*
- **Evidence:** `docs/INFRA_HARDENING_GUIDE.md` schedules `pg_restore_drill.sh` monthly but VPS crontab not grep-confirmed. "Untested backup = no backup."
- **Action:** `ssh root@vps crontab -l | grep pg_restore_drill`; add if missing. Pure ops, no code.
- **Risk:** L (ops task).

---

## Already-handled (NOT gaps — do not re-build)
Dead-man trio (heartbeat/revive/watchdog) · self_improve `acks_late=False` + Redis NX lock + cost-cap + approval-gate · `run_staff_job` `@idempotent_task` · flow_triggers slot-dedupe · `live_eval`/`campaign_optimizer` → eval_gate · `validate_production_settings` (secrets) · auto-rollback health-gate in deploy loop. **Verdict (both discovery agents): infra + agent-workflow = MATURE & DEFENDED; gaps are surgical, not systemic.**
