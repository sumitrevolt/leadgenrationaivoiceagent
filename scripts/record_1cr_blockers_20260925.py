"""Record the 2026-09-25 1CR blocker-clearing work in the canonical task ledger.

Idempotent: matches on an existing title prefix so a re-run updates rather than
duplicating. No duplicate tasks are created for lanes other agents already own
(the 24h LANE rows and the in-flight PRs are left untouched).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Running as `python scripts/<file>.py` puts scripts/ on sys.path, not the repo
# root, so `app` is not importable. Put the root first.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.admin.services.task_ledger import (
    Priority,
    Status,
    TaskCreate,
    TaskUpdate,
    create_task,
    list_tasks,
    update_task,
)

OWNER = "hermes"

ENTRIES = [
    {
        "title": "1CR-BLK-OMNI-CREDS-CLEARED-20260925: OmniRoute 3-layer outage fixed - creds seeded, 476 slots pruned, 112 repointed, 14/14 combos 142-386ms",
        "priority": Priority.P0,
        "status": Status.DONE,
        "description": (
            "FULLY FIXED AND VERIFIED. THREE stacked faults, each masked by the "
            "one above. (1) provider_connections was EMPTY (also provider_nodes, "
            "registered_keys) -> 'No active credentials for provider: anthropic'. "
            "Keys were present in the leadgen_app container env; the gateway had "
            "none. (2) Each combo declared 42 model slots across 42 providers but "
            "only 6 had credentials, so every request walked ~36 credential-less "
            "providers. (3) The surviving slots named RETIRED models: groq 404 on "
            "llama-3.3-70b-versatile, cerebras 404 on llama-3.3-70b, Google "
            "'gemini-2.5-pro is no longer available to new users'. Why self-heal "
            "missed all three: it reseeds COMBOS and syncs LOCAL client config, "
            "never the gateway credential store, and printed '[OK] seed skipped'; "
            "its /api/health probe hit a 404 that surfaced as '401 Unauthorized'. "
            "RESULT: combos 1-14 all OK at 142-386ms (were 45s timeouts), real "
            "reply 'content':'PONG' with finish_reason=stop, 8 live failover slots "
            "across 5 providers per combo. Idempotency proven live: re-running "
            "each script reports 0 changes. leadgen_app never restarted or "
            "redeployed."
        ),
        "evidence": {
            "gateway_db": "/var/lib/docker/volumes/leadgen_omniroute_data/_data/storage.sqlite",
            "provider_connections": "0 -> 6 (cerebras, gemini, groq, mistral, nvidia, openrouter)",
            "credential_less_slots_dropped": 476,
            "slots_repointed": 112,
            "combos_verified": "14/14 OK, 142-386ms",
            "real_completion": '"content":"PONG", finish_reason=stop',
            "failover_depth": "8 live slots across 5 providers per combo",
            "idempotency": "re-run reports 0 changes on all four gateway scripts",
            "backups": [
                "storage.sqlite.bak-seedproviders-20260925_105807",
                "storage.sqlite.bak-pruneslots-<ts>",
                "storage.sqlite.bak-repoint-<ts>",
            ],
            "branch": "fix/omniroute-credential-recovery",
            "commit": "3681fdcbc0e17a11021fe7e7ef15b229f41f5453",
            "prod_untouched": "leadgen_app b5d806fe, /health + /health/ready 200, never restarted",
        },
    },
    {
        "title": "1CR-BLK-HARNESS-FALSEHEALTH-20260925: admin harness health/self-heal reported OK while gateway could not infer",
        "priority": Priority.P1,
        "status": Status.DONE,
        "description": (
            "Two false-green paths in scripts/leadgen_admin_harness_mcp.py. "
            "(1) tool_omniroute_health_check probed /api/health, which the "
            "Next.js gateway does not serve -> 404 surfaced as '401 "
            "Unauthorized' and read as gateway down; it now probes /v1/models. "
            "(2) tool_omniroute_self_heal only re-seeded combos and local client "
            "config, printing '[OK] seed skipped' while inference stayed broken; "
            "it now performs a real post-heal inference and returns "
            "[VERIFIED]/[INCOMPLETE] with the exact remediation command. Both "
            "tools now prove inference instead of model-list liveness."
        ),
        "evidence": {
            "file": "scripts/leadgen_admin_harness_mcp.py",
            "fixed_tools": ["tool_omniroute_health_check", "tool_omniroute_self_heal"],
            "false_positive_symptom": "401 Unauthorized on a live gateway",
        },
    },
    {
        "title": "1CR-BLK-CI-RATCHET-20260925: prod_check + Pytest red on 29/30 open PRs from one shared root cause",
        "priority": Priority.P0,
        "status": Status.IN_PROGRESS,
        "description": (
            "TRIAGED TO EXACT FINGERPRINTS, NOT YET FIXED. 29 of 30 open PRs fail "
            "the identical pair 'prod_check runtime gates' + 'Pytest Tests', so this "
            "is ONE root cause, not 29 problems. prod_check fails with 'RATCHET "
            "FAILED': baseline_fingerprints=788, unresolved_now=988, "
            "newly_unresolved=9, regressions=0, removed=6. Reproduced locally on a "
            "clean origin/main worktree (b5d806fe) via "
            "'scripts/runtime_data_path_scan.py ratchet' (note: ratchet is a "
            "POSITIONAL arg, not --mode). The 9 are: "
            "7 in dead pilot scripts under scripts/legacy/ "
            "(pilot_dispatch_0830_1455.py READ+REWRITE, pilot_nudge_run.py "
            "READ+REWRITE, pilot_run_tick.py READ+REWRITE on "
            "command_center/data/tasks.json) and 2 in live platform files: "
            "app/platform/telegram_coordinator.py:361 tmp REPLACE "
            "_LEASE_PATH.with_suffix('.tmp') (an atomic-write lockfile, same "
            "store as the .json), and app/platform/typesafe_integration.py:128 "
            "READ data/typesafe_keys.json (the exact store PR #565 already "
            "classifies as TIER_NONE + secret-config, non-blocker). All 9 are "
            "PRESENT ON CLEAN MAIN, so this is BASELINE STALENESS, not new code. "
            "SECOND, SEPARATE FAILURE: "
            "tests/test_video_approval_bypass_containment.py:65 "
            "_no_repo_data_writes fails 'repo data/ mutated' on "
            "automation_logs.jsonl, job_heartbeats.json, job_runs.jsonl under CI's "
            "'pytest -n auto' but passes in isolation -- background job writers "
            "touch the REAL repo data/ during the parallel run. "
            "NOT auto-fixed on purpose: regenerating the baseline is a GOVERNED "
            "action (runtime_data_baseline_gen.py is deliberately not wired into "
            "CI) and needs reviewed records in "
            "runtime_data_baseline_changes.CHANGES. Auto-absorbing would silence "
            "the ratchet by design."
        ),
        "evidence": {
            "prs_failing": 29,
            "prs_total_open": 30,
            "pr_passing": "580 (upi-submit-persistence-truth)",
            "ratchet": {
                "baseline_fingerprints": 788,
                "unresolved_now": 988,
                "newly_unresolved": 9,
                "regressions": 0,
                "removed_since_baseline": 6,
            },
            "new_finding_files": [
                "app/platform/telegram_coordinator.py (tmp REPLACE .tmp lockfile)",
                "app/platform/typesafe_integration.py (READ data/typesafe_keys.json)",
                "scripts/legacy/pilot_dispatch_0830_1455.py (READ+REWRITE)",
                "scripts/legacy/pilot_nudge_run.py (READ+REWRITE)",
                "scripts/legacy/pilot_run_tick.py (READ+REWRITE)",
            ],
            "repro_cmd": "python scripts/runtime_data_path_scan.py ratchet",
            "clean_main_worktree": "C:/c/tmp/ci-rootfix @ b5d806fe",
            "pytest_failure": (
                "tests/test_video_approval_bypass_containment.py:65 "
                "repo data/ mutated - automation_logs.jsonl, "
                "job_heartbeats.json, job_runs.jsonl (only under -n auto)"
            ),
        },
    },
    {
        "title": "1CR-BLK-BUZZ-RELAY-20260925: cross-agent Buzz coordination channel is down (buzz.exe missing)",
        "priority": Priority.P2,
        "status": Status.BLOCKED,
        "description": (
            "The Buzz MCP tools answer channel/lock queries (relay ws://"
            "127.0.0.1:3100, 8 channels, no LOCKS.json) but mcp__buzz__buzz_send "
            "fails with 'buzz.exe missing (LOCALAPPDATA\\\\Buzz\\\\buzz.exe) - "
            "install Buzz Desktop'. So cross-agent coordination posts cannot be "
            "delivered and other agents' channel traffic cannot be read. This is "
            "the only coordination surface besides the Telegram control view, so "
            "it directly limits the 'sync with existing agent work' requirement. "
            "Needs Buzz Desktop installed or the relay path repaired. No code fix "
            "attempted: the missing component is the external binary, not a bug "
            "in this repo."
        ),
        "evidence": {
            "error": "buzz.exe missing (LOCALAPPDATA\\Buzz\\buzz.exe) - install Buzz Desktop",
            "tool": "mcp__buzz__buzz_send",
            "working": "buzz_channels, buzz_lock_status",
            "relay": "ws://127.0.0.1:3100",
            "channels": 8,
        },
    },
    {
        "title": "1CR-BLK-LOCALHEAD-20260925: main worktree on unborn branch feat/agnes-final with 5160 dirty paths",
        "priority": Priority.P1,
        "status": Status.BLOCKED,
        "description": (
            "The primary worktree HEAD points at refs/heads/feat/agnes-final, which "
            "has NO commits ('fatal: your current branch 'feat/agnes-final' does "
            "not have any commits yet'), while git status reports 5160 changed "
            "paths. No work can be committed or diffed reliably from this "
            "worktree. 37 worktrees are registered, 10+ locked. All verification "
            "this session was therefore done in a clean origin/main worktree at "
            "C:/c/tmp/ci-rootfix (b5d806fe). Needs an owner decision: the 5160 "
            "dirty paths are uncommitted work of unknown authorship and MUST NOT "
            "be discarded or blanket-committed (R7 forbids git add -A)."
        ),
        "evidence": {
            "branch": "feat/agnes-final",
            "commits": 0,
            "dirty_paths": 5160,
            "worktrees_registered": 37,
            "clean_verification_worktree": "C:/c/tmp/ci-rootfix @ b5d806fe",
        },
    },
]

MARK = "20260925"


def main() -> None:
    existing = list(list_tasks())
    for e in ENTRIES:
        # Idempotency: a task created by a previous run of this script carries
        # the same title, so reuse it instead of adding a second row.
        prior = next((t for t in existing if t.title == e["title"]), None)
        # TaskCreate.evidence is typed as str, so the structured evidence dict is
        # serialized as JSON rather than passed through.
        fields = dict(e)
        if isinstance(fields.get("evidence"), dict):
            fields["evidence"] = json.dumps(fields["evidence"], indent=2, sort_keys=True)

        if prior is not None:
            # A row from a previous run of this script carries the same title.
            # Refresh it instead of adding a duplicate, so a re-run after
            # sharpening the diagnosis actually propagates.
            upd = TaskUpdate(
                description=fields["description"],
                status=fields["status"],
                priority=fields["priority"],
                evidence=fields["evidence"],
            )
            update_task(prior.id, upd)
            print(f"  updated: {e['title'][:66]}")
            continue

        created = create_task(TaskCreate(**fields))
        print(f"  created: {e['title'][:70]}")

    print(f"\nledger now has {len(list_tasks())} tasks")


if __name__ == "__main__":
    main()
