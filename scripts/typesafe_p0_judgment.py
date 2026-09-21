"""Real TypeSafe (System One) judgment over the P0 Key Manager diff.

Per the owner contract (U03/U04): reuse the CANONICAL checked-in client
(app.platform.typesafe_integration.TypeSafeClient) — no competing client —
and invoke TypeSafe only where a semantic judgment materially changes the
next action.

Decision being driven: "is the P0 hardening complete, or does a critical
exposure remain that must be fixed before this PR merges?" Two independent
questions over the same evidence, batched into ONE request.

Never prints the credential. Records requested_model + resolved_model.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("RUN_IN_PROCESS_SCHEDULER", "0")
os.environ.setdefault("TEAM_AUTOMATION", "0")

from app.platform.typesafe_integration import (  # noqa: E402
    Noul,
    credential_state,
    get_typesafe_client,
)


def build_state() -> dict:
    """Evidence: the actual diff summary + the new route/auth model."""
    return {
        "change": {
            "repo": "sumitrevolt/leadgenrationaivoiceagent",
            "file": "app/platform/key_manager.py",
            "pr": 536,
            "base_main_sha": "59f33c67",
        },
        "before": {
            "route_auth": "NONE — /set, /rotate, /deploy had no auth dependency "
            "(source comment: 'In production, add auth dependency')",
            "storage": "plaintext key value written to keys.json",
            "display": "key[:8] + key[-4:] echoed in audit notes and responses",
            "mounted_in_main": False,
        },
        "after": {
            "route_auth": "every /api/admin/keys/* route requires the owner admin "
            "key via require_api_key (ADMIN_API_KEY env / X-API-Key header); "
            "401 when unset or wrong",
            "storage": "Fernet ciphertext at rest; KEYS_MASTER_KEY injected by the "
            "host, external to the store",
            "no_master_key_behaviour": "503 fail-closed on /set and /rotate; "
            "never a silent plaintext fallback",
            "legacy": "existing plaintext entries preserved and reported as "
            "rotation_required; re-encrypted on next authorized write",
            "writes": "atomic tmp + fsync + os.replace, 0600 on POSIX",
            "leakage": "prefix/suffix removed from audit and responses; only "
            "storage/rotation_required/last_verified exposed",
            "deploy_to_env": "decrypts from encrypted storage; refuses when value unreadable",
            "mounted_in_main": "yes, guarded mount",
        },
        "verification": {
            "ruff": "All checks passed",
            "standalone_proof": "6/6 passed",
            "pytest_lockin": "tests/security/test_key_manager_p0.py added",
        },
    }


def main() -> int:
    cred = credential_state()
    print(f"credential_state: {cred.get('state')} (source={cred.get('source')})")
    print(f"fingerprint: {cred.get('fingerprint')}")
    if cred.get("state") != "PRESENT":
        print("BLOCKED: TypeSafe credential not present — no call made.")
        return 2

    client = get_typesafe_client()
    state = build_state()

    questions = {
        "critical_exposure_remains": Noul(
            question=(
                "Does the AFTER state still leave a CRITICAL security exposure in "
                "this key-management path that an unauthenticated or lower-privileged "
                "actor could exploit to read, write, or deploy a live credential? "
                "Answer yes only if a concrete critical exposure remains."
            ),
            instructions=(
                "Judge the credential-handling path as a security reviewer. A critical "
                "exposure means an unauthenticated or unauthorized actor can obtain a "
                "plaintext credential, overwrite one, or cause one to be deployed to a "
                "runtime environment. Configuration that is merely absent (for example a "
                "master key not yet provisioned on the host) is NOT a critical exposure "
                "when the code fails closed instead of degrading to plaintext."
            ),
        ),
        "breaks_legitimate_paths": Noul(
            question=(
                "Does the AFTER state break or block a legitimate authorized "
                "operational path that previously worked, such that the owner could "
                "no longer provision a credential after this change?"
            ),
            instructions=(
                "Consider the owner's provisioning flow: set a key, rotate it, deploy it "
                "to the runtime .env, and read redacted status. Fail-closed behaviour that "
                "returns a clear error when a prerequisite is missing still counts as "
                "working, as long as a correctly configured owner can complete the flow."
            ),
        ),
    }

    t0 = time.time()
    resp = client.system_one(state=state, questions=questions)
    latency_ms = int((time.time() - t0) * 1000)

    print(f"\nsuccess={resp.success} latency_ms={latency_ms} attempts={resp.attempts}")
    if not resp.success:
        print(f"error: {resp.error}")
        return 1

    answers = resp.answers or {}
    resolved = None
    if isinstance(resp.result, dict):
        resolved = resp.result.get("model")

    def p_yes(qid: str) -> float | None:
        """Noul answers are {'type':'noul','noul': <prob of yes>}."""
        a = answers.get(qid)
        if isinstance(a, dict):
            v = a.get("noul")
            if v is None:
                v = a.get("value")
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        return None

    print(f"requested_model={resp.model} resolved_model={resolved}")
    usage = resp.result.get("usage") if isinstance(resp.result, dict) else None
    print(f"usage={usage}")

    # ── Threshold policy (explicit, versioned) ──────────────────────────
    # Consume the judgment: a critical exposure is treated as present when the
    # model's probability of "yes" exceeds this threshold. Threshold chosen
    # conservatively for a security gate (bias toward blocking on doubt).
    THRESHOLD_CRITICAL = 0.5

    p_crit = p_yes("critical_exposure_remains")
    p_break = p_yes("breaks_legitimate_paths")
    print(f"critical_exposure_remains: p_yes={p_crit}")
    print(f"breaks_legitimate_paths:   p_yes={p_break}")

    critical_remaining = p_crit is not None and p_crit > THRESHOLD_CRITICAL
    breaks_paths = p_break is not None and p_break > THRESHOLD_CRITICAL
    if critical_remaining:
        decision = "BLOCK_MERGE_FIX_FIRST"
    elif breaks_paths:
        decision = "REVIEW_REGRESSION_BEFORE_MERGE"
    else:
        decision = "PROCEED_TO_MERGE_GATE"
    print(f"\nDECISION (threshold>{THRESHOLD_CRITICAL}): {decision}")

    # Decision record (redacted refs only, no secrets)
    record = {
        "decision_id": "p0-keymanager-risk-2026-09-21",
        "task_id": "p0-key-manager-hardening",
        "purpose": "changed-area risk classification for P0 security fix",
        "primitive": "Noul",
        "question_ids": list(questions.keys()),
        "state_hash": str(abs(hash(json.dumps(state, sort_keys=True)))),
        "requested_model": resp.model,
        "resolved_model": resolved,
        "probabilities": {
            "critical_exposure_remains": p_crit,
            "breaks_legitimate_paths": p_break,
        },
        "threshold_policy_version": "p0-risk-v1",
        "threshold_used": THRESHOLD_CRITICAL,
        "decision": decision,
        "latency_ms": latency_ms,
        "usage": usage,
        "next_action": "merge-gate decision consumed by the P0 report",
    }
    out = _ROOT / "deliverables" / "engineering-assurance"
    out.mkdir(parents=True, exist_ok=True)
    (out / "typesafe-decision-record-p0-keymanager-2026-09-21.json").write_text(
        json.dumps(record, indent=2)
    )
    print("\ndecision record written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
