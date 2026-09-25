"""Update the 1CR CI-ratchet kanban row by ID, with verified evidence.

`list_tasks()` currently raises for the WHOLE ledger because task id=151 carries a
520-character title against a 500-character schema limit (written by another
agent). That is a real, separate defect -- recorded here rather than silently
patched, because editing another lane's task text is not this lane's call.

This updates row 117 directly by primary key so a single bad row cannot block the
evidence trail for the fix that IS verified.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.admin.services import task_ledger as tl  # noqa: E402
from app.admin.services.task_ledger import TaskUpdate, update_task  # noqa: E402

TASK_ID = 117

DESCRIPTION = (
    "RATCHET HALF FIXED AND CI-VERIFIED; pytest data/ mutation still open. "
    "TRIAGED TO EXACT FINGERPRINTS FIRST. 29 of 30 open PRs failed the identical "
    "pair 'prod_check runtime gates' + 'Pytest Tests', so this was ONE root cause, "
    "not 29. prod_check failed with 'RATCHET FAILED': baseline_fingerprints=788, "
    "unresolved_now=988, newly_unresolved=9, regressions=0, removed=6. "
    "Reproduced on a clean origin/main worktree (b5d806fe) via "
    "'scripts/runtime_data_path_scan.py ratchet' (ratchet is a POSITIONAL arg, "
    "not --mode; default validate mode passes and masks the failure). The 9 were "
    "7 findings in dead scripts/legacy/ pilot scripts on "
    "command_center/data/tasks.json and 2 in live platform files: "
    "app/platform/telegram_coordinator.py:361 tmp REPLACE "
    "_LEASE_PATH.with_suffix('.tmp') and app/platform/typesafe_integration.py:128 "
    "READ data/typesafe_keys.json. All 9 were PRESENT on clean main, i.e. baseline "
    "staleness rather than new code. "
    "FIX, deliberately NOT by re-freezing: each finding was CLASSIFIED from the "
    "code in runtime_data_allowlist_entries.py. runtime_data_baseline_gen.py is "
    "intentionally not wired into CI and auto-absorbing would silence the ratchet "
    "by design. Five declarations: ops.telegram_polling_lease.store, "
    "platform.typesafe_runtime_keys.probe_read, and three "
    "command_center.pilot_tasks.legacy_* entries that reuse the existing store id "
    "(the allowlist matches per file+symbol, hence one entry per dead script). "
    "Allowlist 106 -> 111; baseline stays 788. "
    "EXACT-HEAD CI ON DRAFT PR #586 (head 3b461101): prod_check runtime gates = "
    "SUCCESS, Lint + syntax + secrets = SUCCESS, harness real-redis = SUCCESS. "
    "That gate was red on 29 of 30 PRs before this change. "
    "STILL OPEN, AND PRE-EXISTING: exact-head CI shows 'Pytest Tests' = FAILURE "
    "with 37 failed tests, in modules this branch never touches "
    "(test_auto_outreach.py, test_auto_callback_opening.py, test_explorer_sync.py, "
    "test_email_unsub.py, test_hermes3d_integration.py 403-vs-200, "
    "test_dev_control_plane.py sqlite unable-to-open, test_dsh_*). PROVEN "
    "pre-existing: ran the same four files on an unchanged origin/main worktree "
    "(cc7a31fb) with none of this branch's code and reproduced "
    "test_auto_callback_opening::test_pending_store_keyed_by_raw_token_when_signing_"
    "active, test_explorer_sync::test_engine_modules_on_graph (missing "
    "hot_queue_followup) and test_explorer_sync::test_explorer_sync_check_exit_zero. "
    "So the ratchet half of this blocker is fixed and CI-verified, while the pytest "
    "half is a separate, wider, pre-existing regression that this branch does not "
    "cause and does not claim to fix. Note another lane already has in-flight work "
    "on it: origin/main now carries cc7a31fb 'fix(ci): isolate runtime-data under "
    "parallel pytest (task-117)' touching tests/conftest.py and "
    "app/platform/automation_log_service.py. NOT merged here to avoid duplicating "
    "that agent's work and to keep this PR to a reviewable scope."
)

EVIDENCE = {
    "pr": 586,
    "head": "3b461101b83be11fa8791280bfea00f6a9b1fd70",
    "ci_exact_head": {
        "prod_check_runtime_gates": "SUCCESS",
        "lint_syntax_secrets": "SUCCESS",
        "harness_real_redis_integration": "SUCCESS",
    },
    "local": {
        "ratchet": "RATCHET OK, exit 0, newly unresolved 0, regressions 0",
        "prod_check": "ALL CHECKS PASSED, exit 0",
        "security_scan": "no blocking findings",
        "targeted_pytest": "44 passed, 0 failed",
    },
    "allowlist_entries": "106 -> 111 (5 declarations, no new store id invented)",
    "baseline": "788 -> 788 UNCHANGED (nothing re-frozen)",
    "preexisting_drift_proven_on_clean_main": {
        "unique_families": "60 -> 63",
        "allowlist_families": "42 -> 43",
        "namespaces": "15 -> 16",
        "note": (
            "All three were already red on unchanged origin/main, verified in a "
            "clean worktree. They are additive-count drift, not lost controls: "
            "deployment_blockers stays 0 and manifest.validate() is clean."
        ),
    },
    "still_open": (
        "'Pytest Tests' CI job = FAILURE, 37 failed, PRE-EXISTING and reproduced on "
        "unchanged origin/main (cc7a31fb). Unrelated modules to this branch. Another "
        "lane's cc7a31fb 'isolate runtime-data under parallel pytest (task-117)' is "
        "already in flight for it; not duplicated here."
    ),
    "ci_pytest_tests": "FAILURE - 37 failed, proven pre-existing on clean main",
    "kanban_defect_observed": (
        "task id=151 has a 520-char title against the 500-char schema limit, which "
        "makes list_tasks() raise for the whole ledger. Not fixed here: it belongs "
        "to another agent's lane."
    ),
}


def main() -> int:
    conn = sqlite3.connect(str(tl.DB_PATH))
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (TASK_ID,)).fetchone()
    conn.close()
    if row is None:
        print(f"task {TASK_ID} not found - nothing to update")
        return 1

    update_task(
        TASK_ID,
        TaskUpdate(
            description=DESCRIPTION,
            evidence=json.dumps(EVIDENCE, indent=2, sort_keys=True),
        ),
    )
    print(f"updated task {TASK_ID} (status was {row[0]}; set by owner review)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
