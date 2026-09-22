"""Real TypeSafe System One judgment over the current LeadGen AI admin state.

INDEPENDENT questions in ONE request (the recommended shape). The answers are
consumed programmatically by the admin loop to drive the NEXT action, so this is
a material decision call — not decoration.

Usage:
    python scripts/typesafe_admin_judge.py

The STATE block below is the ONLY thing that should change between runs: keep it
strictly to facts that were verified live in the current session, and date them.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # .../scripts
REPO = ROOT.parent                              # repo root
sys.path.insert(0, str(REPO))                   # for `app.*`
sys.path.insert(0, str(ROOT))                   # for sibling scripts

# Sanctioned local-admin credential bootstrap (never prints the value).
from typesafe_admin_triage import bootstrap_local_credential  # noqa: E402

src, fp = bootstrap_local_credential()
print(f"[credential] source={src} fingerprint={fp}")

from app.platform.typesafe_integration import (  # noqa: E402
    Choice,
    Noul,
    Score,
    typesafe_system_one,
)

# --------------------------------------------------------------------------
# Verified live 2026-09-21/22. Do not add unverified claims here.
# --------------------------------------------------------------------------
STATE = {
    "objective": "₹1,00,00,000 net collected cash per operating month across the owner's projects.",
    "business_reality": {
        "paying_customers": 1,
        "prices_inr_per_month": [1999, 5999, 4999, 9999, 19999],
        "payment_rail": "manual UPI only; owner confirms bank credit; no provider webhook",
        "outbound_calling": "DLT-gated and HARD OFF for cold outbound",
        "email_cap": "25 contacts/day (OUTREACH_DAILY_CAP)",
    },
    "known_revenue_blockers": {
        "smartflo_did_voice_destination": (
            "null — inbound calls are dead. Setting it is a CONSOLE action: a POST to the "
            "Smartflo API returns 422, so there is no API path. Owner-only, not automatable."
        ),
        "upi_confirmation": "manual, owner-attention bound",
    },
    "repo_facts_verified_2026_09_22": {
        "visibility": "PUBLIC",
        "remote_main": "e91e45e6 (fix(compose): WEB_CONCURRENCY env-driven, default 1, PR #549)",
        "production_running": "2962d26e — verified via /health version field; one commit behind main",
        "open_prs": 12,
        "dependabot_alerts_on_default_branch": "15 (1 critical, 5 high, 9 moderate)",
        "required_status_checks": ["Lint + syntax + secrets", "harness real-redis integration"],
        "pytest_job_exists_but_not_required": True,
    },
    "security_facts": {
        "leaked_credentials": (
            "TWO live Telegram credentials were committed on PUBLIC main: (1) the MTProto "
            "api_id/api_hash in 8 places across 6 files, (2) a TELEGRAM_WEBHOOK_SECRET "
            "(48-hex, marked 'LIVE and verified') in docs/TELEGRAM_ENTERPRISE_SETUP_COMPLETE.md"
        ),
        "remediation_status": (
            "PR #550 (branch security-scrub-telegram-creds) removes ALL 9 occurrences. Diff is "
            "9 files, +420/-40. Verified: 0 occurrences of either value on the branch, py_compile "
            "OK on all 4 scripts, fail-closed guard proven by execution (env unset -> exit 2), "
            "scanner suites 40/40 pass, ruff format clean."
        ),
        "scanner_blind_spot": (
            "check_secrets.py could not detect either leak. Root cause: the label is a SUFFIX of a "
            "longer underscore-joined identifier, so the generic pattern's bare \\b anchor never "
            "matched (no word boundary before API inside TELEGRAM_API_HASH). A naive widening with "
            "\\b\\w* was tried and MEASURED: 225 new repo-wide findings, ~220 false positives "
            "(.secrets.baseline SHA-1 hashes alone ~215). Final design adds ONE narrowly-scoped "
            "suffix-label pattern instead; measured delta is exactly 1 new finding and it is the "
            "real webhook secret. 0 false positives."
        ),
        "residual": (
            "both values remain in main's git history regardless of the merge; rotating the api_hash "
            "at my.telegram.org and re-registering the webhook with a new secret are owner-only "
            "(phone/SMS) and NOT yet done"
        ),
    },
    "telegram_facts_verified_2026_09_22": {
        "notify_token": "AUTHENTICATED (@LeadgenaiNotify_bot id 8773095142); old token was HTTP 401",
        "coordination_groups": {
            "workers_coordination": -1003951449805,
            "agents_coordination": -1004368756403,
            "admin_command_center": -1004387221522,
        },
        "vps_ingress": "heartbeat state=polling (was external_conflict, conflicts 38 -> 1)",
        "end_to_end": "a /status sent to @Sumits_jarvis_bot was ingested and answered within 5s",
        "residual": (
            "the available MTProto session belongs to the grid-admin account 8687893086, not owner "
            "1621120182; the owner-account command path is UNPROVEN"
        ),
    },
    "cleanup_facts": {
        "hermes3d": "29,725+ files, 0 tracked, gitignored, BUT has a live bridge app/platform/hermes3d_bridge.py",
        "admin_dashboard": "10,223 files, 43 tracked, real deployable React surface",
        "regenerable": [".mypy_cache", ".pytest_cache", ".ruff_cache", "app/graphify-out", "graphify-out"],
        "scratch_scripts_in_scripts_dir": (
            "58 underscore-prefixed files. IMPORTANT: many are LOAD-BEARING — "
            "app/platform/deployment_path_manifest.py, app/platform/runtime_data.py and four test "
            "files reference them. Only the ~15 untracked session scratch files (_tmp_diag*.sh, "
            "_vps_*.sh, _head_check_state.py, ...) are disposable."
        ),
        "agile_duplicate": "AGENTS.md and CLAUDE.md are byte-identical",
    },
}

questions = {
    "next_action": Choice(
        "Which single next action should the admin take first?",
        {
            "rotate_credentials": "Owner rotates BOTH leaked Telegram credentials (api_hash + webhook secret)",
            "merge_pr_550": "Merge PR #550 to stop both credentials sitting on PUBLIC main",
            "fix_smartflo": "Fix the Smartflo DID->VOICE destination so inbound calls work",
            "harden_ci": "Add the existing Pytest Tests job to required status checks",
            "triage_open_prs": "Triage the 13 open PRs and the 15 dependabot alerts",
            "quarantine_scratch": "Move the untracked session scratch scripts out of scripts/",
        },
    ),
    "scanner_design_correct": Noul(
        "Given the measured facts — a naive widening of the generic patterns produced 225 repo-wide "
        "findings of which ~220 were false positives, while the final dedicated suffix-label pattern "
        "produced exactly 1 new finding which was a real leaked credential and 0 false positives — "
        "is the dedicated-pattern design the correct approach to have shipped?",
        STATE,
    ),
    "merge_pr550_now": Noul(
        "Given that the branch diff is 9 files, both credentials are absent from the branch, all "
        "scripts compile, the fail-closed guard is proven by execution, the scanner suites pass "
        "40/40, and the PR's own CI checks are still in flight, is PR #550 ready to be merged right "
        "now without waiting for its checks to finish?",
        STATE,
    ),
    "highest_revenue_lever": Score(
        "Rank each candidate work item by its expected contribution to the ₹1 crore net-collected-cash "
        "objective, using only the supplied facts. Highest expected contribution first.",
        [
            "Owner rotates both leaked Telegram credentials",
            "Merge PR #550 to stop the credentials sitting on PUBLIC main",
            "Owner sets the Smartflo DID->VOICE destination (console-only, no API)",
            "Reduce the manual UPI confirmation bottleneck",
            "Add the Pytest Tests job to required status checks",
            "Quarantine the untracked session scratch scripts",
        ],
    ),
    "leak_contained": Noul(
        "Do the supplied verified facts establish that the leaked-credential incident is CONTAINED — "
        "i.e. the exposure is closed and no further agent-side action is required?",
        STATE,
    ),
}

resp = typesafe_system_one(STATE, questions)

print("\n=== TYPESAFE SYSTEM ONE RESPONSE ===")
print("requested_model:", getattr(resp, "requested_model", None))
print("resolved_model :", getattr(resp, "resolved_model", None))
print("latency_sec    :", getattr(resp, "latency_sec", None))
print("success        :", getattr(resp, "success", None))

answers = getattr(resp, "answers", None)
if answers is None:
    answers = getattr(resp, "answer", None)
print("\n--- typed answers ---")
print(json.dumps(answers, indent=2, ensure_ascii=False, default=str))
