# Agnes Desktop — Execution Evidence Report (task AGNES-DESKTOP-001)

> This report is written to distinguish four clearly different states:
> **EXECUTED** (observed tool output this session), **LOCAL-TESTED** (isolated
> pytest harness), **CONFIGURED/READY** (code is in place but not yet live),
> and **UNVERIFIED** (no evidence yet). Nothing here claims a capability that
> is only one of the weaker states.

Date: 2026-09-23 (IST)
Branch: `feat/agnes-final`
HEAD: `d4101b5aa70979048a2fa307558aabab647b6db0`
PR: [#563](https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/563) (created + verified via `gh`)

---

## 1. EXECUTED — direct tool output this session

| Item | State | Evidence |
|---|---|---|
| Shell (Windows CMD) | EXECUTED | `echo/whoami/cd/ver` returned real output; Python 3.11.14 in `.venv` |
| Filesystem | EXECUTED | read + wrote 5 files under the isolated worktree `.worktrees/agnes-desktop-d4101b5a` |
| GitHub branch push | EXECUTED | `git ls-remote origin feat/agnes-final` → `d4101b5a` |
| PR creation + verification | EXECUTED | `gh pr create` → **PR #563**; `gh pr view 563` → head `feat/agnes-final`, base `main`, head SHA `d4101b5a`, MERGEABLE, 5 changed files |
| Ruff lint on changed files | EXECUTED | `ruff check` on 4 Python files → **All checks passed** (after autofix of W293/I001) |
| Test run (forward/CI order) | EXECUTED | `pytest test_agnes_adapter.py test_agnes_mission_lifecycle.py test_agnes_comprehensive.py` → **21 passed** |
| TypeSafe credential + health probe | EXECUTED | `scripts/typesafe_status.py --probe` → credential PRESENT, resolved model `jev-1.13.0`, health reachable, latency ~0.7s |
| VPS reachability | EXECUTED | `ssh root@<vps> uptime` + `docker ps` → 42 containers up; `GET /health` → healthy |

These are things actually observed, not simulations.

## 2. LOCAL-TESTED — isolated harness, not live coordination

- **Real external mission lifecycle** (`test_full_mission_lifecycle_end_to_end`):
  create → preflight → claim(lease) → heartbeat → start(RUNNING) →
  submit_result → submit_review → **REVIEW_PASSED**, with:
  - lease ownership enforced (foreign owner heartbeat rejected),
  - fencing (non-lease-owner `submit_result` → `lease_not_owned`),
  - review separation (executor name self-approve → `review_rejected`),
  - duplicate-mission idempotency,
  - stale-transition rejection,
  - results persisted and retrievable from the **isolated** `EXTERNAL_MISSION_DIR`
    temp store (the internal automation ledger is *not* touched).
- Honest boundary: the local run stops at `REVIEW_PASSED`. The remaining states
  (`PR_OPEN → CI_RUNNING → MERGE_QUEUED → MERGED → VERIFIED → COMPLETE`) each
  require a **real external event** (opened PR, green CI, a merge, a deploy).
  Those are NOT fabricated; the test asserts the valid transition map governs
  them instead of force-advancing to `COMPLETE`.
- **Production-ledger isolation test** confirms the store root resolves to the
  fixture's temp dir, not the in-checkout `data/external_missions`.

## 3. CONFIGURED / READY — code present, not yet live

- `AgnesAdapter` is registered in `app/dev_control/external_agents/adapters.py`
  and participates in the **canonical** external-agent orchestrator
  (no second orchestrator/queue/registry/Telegram poller was introduced).
- Remote/cross-environment execution of an Agnes mission is **not** demonstrated:
  `EXTERNAL_AGENT_ORCHESTRATOR` is off by design in production, and the live
  executor-handshake security fixes (M020 PR #562) are not yet merged/verified.
  Agnes is an authorized *external executor* under the existing coordinator,
  not an added specialist agent.

## 4. UNVERIFIED / BLOCKED

- **Windows GUI automation**: no mouse/keyboard executor available in this
  session. **UNAVAILABLE** — not demonstrated.
- **Telegram live delivery to owner**: Jarvis bot in STANDBY due to HTTP 409
  lease conflicts (an external getUpdates consumer holds the token lease);
  Notify bot 401 (separate invalid credential). **UNVERIFIED** pending owner
  configuration (`TELEGRAM_INGRESS_OWNER`) and Notify token rotation. No new
  poller was started.
- **Live canonical task assigned + executed by Agnes**: **UNVERIFIED** — blocked
  by the off-by-design orchestrator flag and the unmerged M020 handshake.
- **GitHub CI for PR #563** (run `35856049205` at head `d4101b5a`, verified this
  session):
  - **PASSING**: Lint + syntax + secrets, Trivy (repo + image), CodeQL,
    GitGuardian, pip-audit, harness real-redis, Analyze (actions/python/js/cs).
  - **Gate A (non-required sketch)** FAILED — `ruff check` W293/I001 on the five
    changed Agnes files → **attributable to this change**, now fixed in the
    working tree (committed after this note; `ruff@0.16.1 check` +
    `ruff@0.16.1 format --check` both clean on the 4 Python files).
  - **Pytest Tests** FAILED — `tests/test_video_approval_bypass_containment.py:65`
    data-mutation guard (`agent_graph.db`, `harness_runs.jsonl` changed), with a
    Redis local-state fallback (`127.0.0.1:6399` connect fail) → **pre-existing
    project issue, unrelated to the Agnes diff**.
  - **prod_check runtime gates** FAILED — `NEW_UNDECLARED_MUTABLE_PATH` in
    `scripts/legacy/pilot_nudge_run.py` / `pilot_run_tick.py`
    (`command_center/data/tasks.json`) → **pre-existing, unrelated to Agnes**.
  - **prod_check + pytest** — aggregation of the two failures above.
  - Conclusion: the only CI failure attributable to this change is the Ruff gate,
    which is fixed locally and will re-run on the next push. The Pytest and
    prod_check failures are pre-existing and out of scope for the Agnes diff.

## 5. TypeSafe — honest separation

- Credential present + health probe: **EXECUTED** (`jev-1.13.0` resolved, reachable).
- A **live `jev-latest` mission-level judgment** consumed into a downstream
  action was **not** executed in this session. The adapter's
  `validate_result` is deterministic Python (not a TypeSafe call), so no TypeSafe
  invocation is claimed for it. Live TypeSafe workflow integration is recorded
  here only as available-to-use, not as done.

## 6. Remaining blockers (precise)

1. Live Agnes task execution — needs `EXTERNAL_AGENT_ORCHESTRATOR` on in a
   validated env + merged M020 handshake security fixes (owner-gated).
2. Telegram live — Jarvis 409 lease owner + Notify 401 (owner config + rotation).
3. GUI computer-use — no authorized GUI executor in session.
4. CI fully green for #563 — wait for running jobs; fix any failures attributable
   to this change.

## 7. Production safety

No production config was changed; no competing Telegram poller started; no
secrets copied between environments; Agnes remains an external executor under
the existing canonical coordinator.
