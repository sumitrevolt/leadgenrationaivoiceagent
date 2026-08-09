# PR Orchestration Pilot (Bernstein-inspired)

**Status:** CODE-PRESENT · INERT by default (flags OFF) · ADR-166
**What it is:** a bounded, manifest-driven, fail-closed repair/verify/cleanup
orchestrator built on the existing PR Factory spine. Bernstein-inspired safety
rails — **not** vendored Bernstein, **not** a second control plane.

**What it is NOT:** it never merges, never deploys, never touches main, never
mutates a worktree it does not own, and does not run without three flags armed.

## Enablement (operator only — CANARY, prod stays OFF)

All three must be `1`:

```dotenv
PR_FACTORY_PILOT_ENABLED=1
PR_FACTORY_ENABLED=1
EXTERNAL_AGENT_ORCHESTRATOR=1
```

While armed, `repair` / `diagnose` / `verify` refuse with exit code 3 and
code `flags_off` when any flag is off.

## Task manifest (JSON only)

Minimal example (see `tests/test_pr_factory_pilot.py::_manifest` for the full shape):

```json
{
  "task_id": "pilot-001",
  "objective": "fix flaky test",
  "owner": "owner@leadsgenai.in",
  "base_branch": "main",
  "task_branch": "fix/pilot-001",
  "worktree_path": "C:/Users/Ratanshila/Documents/_leadgen_worktrees/pilot-001",
  "allowed_paths": ["tests/test_demo.py"],
  "denied_paths": [],
  "risk_class": "GREEN",
  "required_tests": ["pytest tests/test_demo.py -q"],
  "required_lint": [],
  "required_security": [],
  "expected_head_sha": "<40-hex of the PR head you pin>",
  "max_repair_attempts": 2,
  "external_action_permissions": {"pull_requests": "write", "actions": "read", "contents": "task_branch_only"},
  "owner_approval_id": "",
  "cleanup_ownership": "task_owned",
  "completion_conditions": ["required checks green"],
  "pr_number": 7
}
```

- `expected_head_sha` must be a real 40-hex pin for repair. Empty or `PENDING`
  is refused — an unpinned branch is unsafe to repair.
- `allowed_paths` / `denied_paths` are validated against protected prefixes in
  `app/dev_control/external_agents/policy.py`. Protected prefixes are never
  overridable. A path both allowed and denied, or an overlap, is refused.
- `required_tests` / `required_lint` / `required_security` accept only
  `pytest`/`ruff`/`scripts` prefixes with no shell metacharacters. They are run
  via `sys.executable -m pytest` / `-m ruff` inside the task worktree.

## CLI

```powershell
python -m tools.pr_factory.pilot.cli validate task.json      # exit 0 ok / 1 refused
python -m tools.pr_factory.pilot.cli diagnose task.json      # read-only (also AMBER)
python -m tools.pr_factory.pilot.cli repair task.json        # bounded repair
python -m tools.pr_factory.pilot.cli verify task.json        # completion gate
python -m tools.pr_factory.pilot.cli cleanup task.json       # remove task worktree
```

Exit codes: `0` ok · `1` refusal (JSON `refused: true`, machine `code`) ·
`2` usage · `3` flags-off.

## Guarantees (each enforced + tested)

| Guarantee | Mechanism |
|-----------|-----------|
| No merge / no deploy | `GitHubOps` and `Pilot` expose no merge/auto-merge/deploy methods; tests assert absence |
| Head pinned | `expected_head_sha` required; mismatch → `head_sha_mismatch` refusal |
| Fresh CI only | `fresh_ci_evidence` matches the exact head SHA; stale → `fresh_ci_required` |
| Attempts bounded | per-head ledger, max `max_repair_attempts` (default 2) → `attempt_cap_exceeded` |
| Protected paths untouched | same prefixes as Owner OS policy; refusal `protected_paths` |
| Command allowlist | pytest/ruff/scripts only, no shell metachars |
| Task-owned worktree only | cleanup requires registered worktree + branch match + clean tree |
| No network under lock | per-task repo lock; push/commit only inside, all `gh` calls outside |
| Diagnosis = no mutation | diagnose mode calls zero worktree/code/push code paths |
| Transient retry first | `gh run rerun --failed`, bounded, before any code repair |

## Files

- `tools/pr_factory/pilot/__init__.py` — flag triple-gate, `MAX_REPAIR_ATTEMPTS`
- `tools/pr_factory/pilot/manifest.py` — JSON manifest validation
- `tools/pr_factory/pilot/guard.py` — fail-closed state machine + repair ledger
- `tools/pr_factory/pilot/github_ops.py` — `gh` wrapper (read + bounded retry/comment; no merge/deploy)
- `tools/pr_factory/pilot/worktree.py` — task-owned worktree lifecycle + guarded cleanup
- `tools/pr_factory/pilot/pilot.py` — orchestration flows
- `tools/pr_factory/pilot/cli.py` — CLI entry
- Tests: `tests/test_pr_factory_pilot*.py`

## Rollback

1. Leave the three flags OFF (default) — pilot is inert.
2. If adopted and later abandoned: delete `tools/pr_factory/pilot/` + the four
   test files. No workflow or branch-protection changes to revert.
