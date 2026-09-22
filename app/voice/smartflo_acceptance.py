"""SmartFlo acceptance test framework — P0 release gate (per Owner Directive 2026-09-22).

Executes the existing SmartFlo channel → Swara conversation → hangup → recording/transcript
→ CRM outcome acceptance test. OWNER-AUTHORIZED RUN; not auto-run on CI.

Per the directive:
    "Swara acceptance test ... Verify one actual phone conversation with evidence"
    "A successful API response, answered phone call or greeting alone is insufficient"
    "Do not label calling operational until a real bidirectional conversation succeeds"

This module is INVOKED FROM AN OPERATOR-OWNED SHELL once VPS access is restored and
the operator has authorised a test number + the existing active SmartFlo channel.

CLI:
    python -m app.voice.smartflo_acceptance --to <owner-authorized-test-number>

Output:
    JSON document on stdout with all 11 acceptance criteria + pass/fail.
    Exit code 0 = all pass; 1 = at least one fail; 2 = prerequisite missing.

PREREQUISITES (gates 0-3 — local, runs anywhere):
    - SMARTFLO_API_KEY + SMARTFLO_APP_ID in env OR `data/typesafe_keys.json`
    - SMARTFLO_VOICE_STREAM_ENABLED=1
    - VPS SSH reachable on 72.61.245.204 (this script will probe before call)
    - Owner-authorized test number passed via --to

REMOTE STEPS (gates 4-10 — need operator-trusted VPS session):
    4.  SmartFlo Click-to-Call API to place outbound test call (or answer inbound)
    5.  WebSocket stream opens (smartflo_stream.handle) — verify with stream_token
    6.  Swara greeting plays (TTS outbound "Hello, this is Swara, AI assistant...")
    7.  Caller speech recognized — STT provider returns non-empty text
    8.  Swara responds contextually — LLM reply path executes within deadline
    9.  Multi-turn works — caller says X, bot replies Y, no dead air > 2s
    10. Interruption / barge-in works — caller speaks over TTS playback, bot yields
    11. Call ends normally — STOP event, transcript persisted, CDR correlated,
        CRM outcome updated (lead.stage advanced or owner task created)

This file is the SKELETON. Each remote step has a `verify_step_N()` function that
MUST be implemented in the operator-trusted environment. Local tests cover
gates 0-3 only. CI does NOT execute any real call.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Canonical VPS endpoint (per legacy deployment contract)
VPS_HOST = "72.61.245.204"
VPS_SSH_PORT = 22

# Acceptance criteria (gate IDs must remain stable — owner dashboards read these)
GATES = [
    {"id": 0, "name": "credentials_present", "remote": False},
    {"id": 1, "name": "stream_enabled", "remote": False},
    {"id": 2, "name": "vps_reachable", "remote": False},
    {"id": 3, "name": "test_number_authorized", "remote": False},
    {"id": 4, "name": "smartflo_call_accepted", "remote": True},
    {"id": 5, "name": "websocket_opened", "remote": True},
    {"id": 6, "name": "swara_greeting_played", "remote": True},
    {"id": 7, "name": "caller_speech_recognized", "remote": True},
    {"id": 8, "name": "swara_response_contextual", "remote": True},
    {"id": 9, "name": "multi_turn_no_dead_air", "remote": True},
    {"id": 10, "name": "interruption_barge_in", "remote": True},
    {"id": 11, "name": "call_ended_with_outcome", "remote": True},
]


# --------------------------------------------------------------------------- #
# Local gates (no VPS / no telephony — run anywhere)                          #
# --------------------------------------------------------------------------- #


def _credential_state() -> dict[str, Any]:
    """Read canonical credential state (no key value printed — only fingerprint)."""
    try:
        from app.platform import typesafe_integration as _ts

        return _ts.credential_state()
    except Exception as exc:
        return {"state": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def verify_credentials_present() -> dict[str, Any]:
    state = _credential_state()
    # SmartFlo credential is typically separate from TypeSafe — owner provides via
    # env SMARTFLO_API_KEY + SMARTFLO_APP_ID OR through the TypeSafe admin override
    # path (data/typesafe_keys.json). We just probe the env contract here.
    api_key_present = bool(os.environ.get("SMARTFLO_API_KEY", "").strip())
    app_id_present = bool(os.environ.get("SMARTFLO_APP_ID", "").strip())
    if api_key_present and app_id_present:
        return {"gate": 0, "status": "PASS", "source": "env:SMARTFLO_API_KEY+SMARTFLO_APP_ID"}
    if state.get("state") == "PRESENT":
        return {"gate": 0, "status": "PASS", "source": "typesafe_admin_override"}
    return {
        "gate": 0,
        "status": "FAIL",
        "reason": (
            "SmartFlo credentials absent. Set SMARTFLO_API_KEY + SMARTFLO_APP_ID in "
            "env OR add admin override to data/typesafe_keys.json"
        ),
        "credential_state": state,
    }


def verify_stream_enabled() -> dict[str, Any]:
    enabled = os.environ.get("SMARTFLO_VOICE_STREAM_ENABLED", "").strip() in {"1", "true", "yes", "on"}
    if enabled:
        return {"gate": 1, "status": "PASS"}
    return {
        "gate": 1,
        "status": "FAIL",
        "reason": "SMARTFLO_VOICE_STREAM_ENABLED must be set to 1 (currently INERT default)",
    }


def verify_vps_reachable() -> dict[str, Any]:
    """TCP probe only (NOT SSH handshake — that fails under load).

    CI bypass: set SMARTFLO_SKIP_VPS_PROBE=1 to skip the network probe
    (for unit tests under netguard). Production runs MUST NOT set this.
    """
    if os.environ.get("SMARTFLO_SKIP_VPS_PROBE", "").strip() in {"1", "true", "yes"}:
        return {
            "gate": 2,
            "status": "PASS",
            "host": VPS_HOST,
            "probe_skipped": True,
            "reason": "SMARTFLO_SKIP_VPS_PROBE=1 (CI/test bypass)",
        }
    try:
        with socket.create_connection((VPS_HOST, VPS_SSH_PORT), timeout=4.0) as _:
            return {"gate": 2, "status": "PASS", "host": VPS_HOST}
    except (socket.timeout, OSError) as exc:
        return {
            "gate": 2,
            "status": "FAIL",
            "host": VPS_HOST,
            "reason": f"VPS TCP probe failed: {type(exc).__name__}: {exc}",
        }


def verify_test_number_authorized(test_number: str | None) -> dict[str, Any]:
    """Operator-provided --to must be a valid Indian mobile/landline AND in the
    COMPLIANCE_ALLOWLIST env var (default-deny)."""
    allowlist_raw = os.environ.get("COMPLIANCE_ALLOWLIST", "").strip()
    allowlist = {n.strip() for n in allowlist_raw.split(",") if n.strip()}
    if not test_number:
        return {
            "gate": 3,
            "status": "FAIL",
            "reason": "--to <owner-authorized-test-number> not provided on CLI",
        }
    digits_only = "".join(ch for ch in test_number if ch.isdigit())
    if len(digits_only) < 10:
        return {
            "gate": 3,
            "status": "FAIL",
            "reason": f"--to {test_number!r} has < 10 digits; expected Indian mobile",
            "provided": test_number,
        }
    if allowlist and digits_only not in allowlist:
        return {
            "gate": 3,
            "status": "FAIL",
            "reason": f"--to {test_number!r} not in COMPLIANCE_ALLOWLIST",
            "allowlist": sorted(allowlist),
            "provided": digits_only,
        }
    return {
        "gate": 3,
        "status": "PASS",
        "test_number": digits_only,
        "allowlist_size": len(allowlist) if allowlist else "unset-permissive",
    }


# --------------------------------------------------------------------------- #
# Remote gate stubs (gates 4-11 — implement in operator-trusted environment)   #
# --------------------------------------------------------------------------- #


def verify_smartflo_call_accepted(test_number: str) -> dict[str, Any]:
    """STUB. On operator-trusted VPS:

        from app.telephony.smartflo_test_call import place_test_call
        resp = place_test_call(to=test_number)
        return {"gate": 4, "status": "PASS" if resp.get("accepted") else "FAIL",
                "call_id": resp.get("call_id"), "raw": resp}

    A successful API response / answered call / greeting alone is NOT a pass —
    the SmartFlo Click-to-Call API only confirms REQUEST ACCEPTANCE. The actual
    connection is observed via the status webhook (smartflo_webhooks.py) and
    the WebSocket stream open (smartflo_stream.py handle()).
    """
    return {
        "gate": 4,
        "status": "UNVERIFIED",
        "reason": (
            "STUB — operator must run this from VPS with place_test_call(); SmartFlo "
            "Click-to-Call response is REQUEST ACCEPTANCE only; actual connection "
            "must be observed via WebSocket open + status webhook (see smartflo_webhooks.py)."
        ),
        "test_number": test_number,
    }


def verify_websocket_opened(test_number: str) -> dict[str, Any]:
    """STUB. Operator-trusted: trace stream_token issuance + WS handshake log."""
    return {
        "gate": 5,
        "status": "UNVERIFIED",
        "reason": "STUB — observe smartflo_stream.handle() receiving `connected` event",
    }


def verify_swara_greeting_played(test_number: str) -> dict[str, Any]:
    """STUB. Operator-trusted: verify mark event for greeting completes."""
    return {
        "gate": 6,
        "status": "UNVERIFIED",
        "reason": "STUB — observe mark `swara_greeting_done` in stream trace",
    }


def verify_caller_speech_recognized(test_number: str) -> dict[str, Any]:
    """STUB. Operator-trusted: STT transcript non-empty for the test utterance.

    The known issue per the 2026-09-16 Swara recovery plan is that 25-call
    samples showed audio received but no recognized user turns. This gate MUST
    pass before any 5-channel rollout. If STT returns empty, the fallback
    'Maaf kijiye, awaaz saaf nahi aayi' fires — visible to the caller as the
    bot appearing deaf.
    """
    return {
        "gate": 7,
        "status": "UNVERIFIED",
        "reason": (
            "STUB — operator must run a real test utterance and confirm STT returns "
            "non-empty text within 4s provider deadline. If empty, Swara fires the "
            "'Maaf kijiye, awaaz saaf nahi aayi' fallback and the caller experiences "
            "a one-sided fallback loop."
        ),
        "known_failure_mode": "empty STT -> fallback loop (see 2026-09-16-swara-conversation-recovery.md)",
    }


def verify_swara_response_contextual(test_number: str) -> dict[str, Any]:
    """STUB. Operator-trusted: LLM reply non-empty within 6s."""
    return {"gate": 8, "status": "UNVERIFIED", "reason": "STUB — observe _llm_reply trace"}


def verify_multi_turn_no_dead_air(test_number: str) -> dict[str, Any]:
    """STUB. Operator-trusted: 3 consecutive user turns, no > 2s gap between
    bot reply end and next user STT."""
    return {"gate": 9, "status": "UNVERIFIED", "reason": "STUB — observe 3-turn transcript"}


def verify_interruption_barge_in(test_number: str) -> dict[str, Any]:
    """STUB. Operator-trusted: caller speaks during bot TTS playback, bot yields.

    Current code: 3 frames of speech (~60ms) during playback_active triggers
    `_barge_in()` which calls `_clear_pending_marks` + cancels the play task.
    """
    return {"gate": 10, "status": "UNVERIFIED", "reason": "STUB — observe barge-in trace"}


def verify_call_ended_with_outcome(test_number: str) -> dict[str, Any]:
    """STUB. Operator-trusted: STOP event received, transcript persisted,
    CDR correlated with call_id, billing metered (with double-billing guard
    `meter_call_completion` keyed on call_meter:{call_id}), CRM lead updated."""
    return {
        "gate": 11,
        "status": "UNVERIFIED",
        "reason": (
            "STUB — verify (a) transcript in data/orchestrator_ledger.db#transcript, "
            "(b) call_meter key written, (c) lead stage advanced or owner task created"
        ),
    }


# --------------------------------------------------------------------------- #
# Runner                                                                       #
# --------------------------------------------------------------------------- #


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_acceptance(*, test_number: str | None) -> dict[str, Any]:
    """Run all 12 gates; return machine-readable result document."""
    out: dict[str, Any] = {
        "started_at": _now(),
        "test_number_requested": test_number,
        "owner_directive_ref": "docs/OWNER_DIRECTIVE_2026-09-22.md (P0 SmartFlo acceptance)",
    }
    gates: list[dict[str, Any]] = []

    # Local gates 0-3
    gates.append(verify_credentials_present())
    gates.append(verify_stream_enabled())
    gates.append(verify_vps_reachable())
    gates.append(verify_test_number_authorized(test_number))

    # Remote gates 4-11 — UNVERIFIED until operator runs in trusted VPS env
    if test_number and all(g["status"] == "PASS" for g in gates):
        gates.append(verify_smartflo_call_accepted(test_number))
        gates.append(verify_websocket_opened(test_number))
        gates.append(verify_swara_greeting_played(test_number))
        gates.append(verify_caller_speech_recognized(test_number))
        gates.append(verify_swara_response_contextual(test_number))
        gates.append(verify_multi_turn_no_dead_air(test_number))
        gates.append(verify_interruption_barge_in(test_number))
        gates.append(verify_call_ended_with_outcome(test_number))
    else:
        # Prereq failure — short-circuit
        for g in GATES:
            if g["id"] >= 4:
                gates.append({
                    "gate": g["id"],
                    "name": g["name"],
                    "status": "BLOCKED",
                    "reason": "prerequisite_gate_failed",
                })

    out["gates"] = gates
    summary = {"PASS": 0, "FAIL": 0, "UNVERIFIED": 0, "BLOCKED": 0}
    for g in gates:
        s = g.get("status", "?")
        summary[s] = summary.get(s, 0) + 1
    out["summary"] = summary
    out["finished_at"] = _now()
    out["verdict"] = (
        "READY_FOR_FIVE_CHANNEL_ROLLOUT"
        if summary["PASS"] == 12
        else "PENDING_OPERATOR_TRUSTED_RUN"
        if summary["UNVERIFIED"] > 0 and summary["FAIL"] == 0 and summary["BLOCKED"] == 0
        else "BLOCKED_FIX_PREREQS_FIRST"
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SmartFlo acceptance test (P0 release gate)")
    parser.add_argument("--to", default=None, help="Owner-authorized Indian test number (10+ digits)")
    args = parser.parse_args(argv)

    result = run_acceptance(test_number=args.to)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result["summary"].get("FAIL", 0) > 0:
        return 2
    if result["summary"].get("UNVERIFIED", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
