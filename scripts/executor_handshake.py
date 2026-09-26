#!/usr/bin/env python3
"""Reference executor handshake client — what a real Hermes Desktop / Agnes
Desktop session would run from its own host to participate in the canonical
task authority.

This is a REFERENCE implementation. The actual Hermes/Agnes Desktop
sessions run as separate Mavis orchestrators on separate Windows hosts.
This script demonstrates the exact protocol they would use.

Per M020:
- Outbound-only from the desktop executor to the coordinator.
- HMAC-authenticated using the existing ``coordination_hub_auth`` machinery.
- Never expose the secret; never bypass deterministic gates.
- A real task claim requires a real desktop session actively polling.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

# Allow this script to live outside the package and still use the canonical
# auth module. Insert the worktree root on sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# --------------------------------------------------------------------------- #
# Local HMAC signing (mirrors coordination_hub_auth.build_tool_signature)
# --------------------------------------------------------------------------- #


def _sign_request(
    secret: str,
    tool_id: str,
    event_type: str,
    body_bytes: bytes,
    issued_at: int,
    nonce: str,
) -> tuple[str, str]:
    """Compute the canonical signature + body_sha256. Returns (sig, body_sha)."""
    from app.platform import coordination_hub_auth as auth

    body_sha = auth.body_sha256(body_bytes)
    sig = auth.build_tool_signature(
        secret=secret,
        tool_id=tool_id,
        event_type=event_type,
        body_sha256=body_sha,
        issued_at=issued_at,
        nonce=nonce,
    )
    return sig, body_sha


def _post(
    url: str, headers: dict[str, str], body_bytes: bytes, timeout: int = 30
) -> dict[str, Any]:
    """POST with stdlib urllib. Returns parsed JSON. Raises on non-2xx."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "_http_error": exc.code,
            "_reason": exc.reason,
            "_body": exc.read().decode("utf-8", errors="replace"),
        }


def _get(url: str, timeout: int = 30) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "_http_error": exc.code,
            "_reason": exc.reason,
            "_body": exc.read().decode("utf-8", errors="replace"),
        }


# --------------------------------------------------------------------------- #
# High-level operations
# --------------------------------------------------------------------------- #


def _build_headers(tool_id: str, event_type: str, body_bytes: bytes, secret: str) -> dict[str, str]:
    issued_at = int(time.time())
    nonce = secrets.token_urlsafe(24)
    sig, body_sha = _sign_request(
        secret=secret,
        tool_id=tool_id,
        event_type=event_type,
        body_bytes=body_bytes,
        issued_at=issued_at,
        nonce=nonce,
    )
    return {
        "Content-Type": "application/json",
        "X-Tool-Id": tool_id,
        "X-Event-Type": event_type,
        "X-Body-Sha256": body_sha,
        "X-Issued-At": str(issued_at),
        "X-Nonce": nonce,
        "X-Signature": sig,
    }


def status(base_url: str) -> dict[str, Any]:
    """Public probe — no auth, returns registered tool list and per-tool configured flag."""
    return _get(f"{base_url}/api/executor/handshake/status")


def next_task(base_url: str, tool_id: str, secret: str) -> dict[str, Any]:
    """Ask the coordinator for the next READY task for this tool."""
    body = json.dumps({}).encode("utf-8")
    headers = _build_headers(tool_id, "executor.next_task", body, secret)
    return _post(f"{base_url}/api/executor/{tool_id}/next-task", headers, body)


def heartbeat(base_url: str, tool_id: str, secret: str, task_id: str) -> dict[str, Any]:
    body = json.dumps({"task_id": task_id}).encode("utf-8")
    headers = _build_headers(tool_id, "executor.heartbeat", body, secret)
    return _post(f"{base_url}/api/executor/{tool_id}/heartbeat", headers, body)


def claim(base_url: str, tool_id: str, secret: str, task_id: str) -> dict[str, Any]:
    body = json.dumps({"task_id": task_id}).encode("utf-8")
    headers = _build_headers(tool_id, "executor.claim", body, secret)
    return _post(f"{base_url}/api/executor/{tool_id}/claim", headers, body)


def complete(
    base_url: str,
    tool_id: str,
    secret: str,
    task_id: str,
    fencing_token: str | None,
    evidence: dict[str, Any],
    success: bool = True,
    error_msg: str | None = None,
) -> dict[str, Any]:
    body = json.dumps(
        {
            "task_id": task_id,
            "fencing_token": fencing_token,
            "evidence": evidence,
            "success": success,
            "error_msg": error_msg,
        }
    ).encode("utf-8")
    headers = _build_headers(tool_id, "executor.complete", body, secret)
    return _post(f"{base_url}/api/executor/{tool_id}/complete", headers, body)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Reference executor handshake client (Hermes / Agnes / etc.)"
    )
    p.add_argument("--base-url", required=True, help="e.g. https://leadsgenai.in")
    p.add_argument("--tool-id", required=True, help="e.g. hermes, agnes, openclaw")
    p.add_argument(
        "--secret-env",
        required=True,
        help="env var holding the HMAC secret (e.g. COORD_HUB_TOOL_HERMES_SECRET)",
    )
    p.add_argument(
        "--action", required=True, choices=["status", "next-task", "heartbeat", "claim", "complete"]
    )
    p.add_argument("--task-id", default=None)
    p.add_argument("--fencing-token", default=None)
    p.add_argument(
        "--evidence-file",
        default=None,
        help="JSON file with the evidence payload for --action complete",
    )
    args = p.parse_args(argv)

    secret = os.environ.get(args.secret_env, "").strip()
    if not secret:
        print(json.dumps({"error": f"{args.secret_env}_unset"}, indent=2))
        return 2

    if args.action == "status":
        out = status(args.base_url)
    elif args.action == "next-task":
        out = next_task(args.base_url, args.tool_id, secret)
    elif args.action == "heartbeat":
        if not args.task_id:
            print(json.dumps({"error": "task_id_required_for_heartbeat"}, indent=2))
            return 2
        out = heartbeat(args.base_url, args.tool_id, secret, args.task_id)
    elif args.action == "claim":
        if not args.task_id:
            print(json.dumps({"error": "task_id_required_for_claim"}, indent=2))
            return 2
        out = claim(args.base_url, args.tool_id, secret, args.task_id)
    elif args.action == "complete":
        if not args.task_id:
            print(json.dumps({"error": "task_id_required_for_complete"}, indent=2))
            return 2
        evidence = {}
        if args.evidence_file:
            evidence = json.loads(Path(args.evidence_file).read_text(encoding="utf-8"))
        out = complete(
            args.base_url,
            args.tool_id,
            secret,
            args.task_id,
            fencing_token=args.fencing_token,
            evidence=evidence,
        )
    else:
        out = {"error": f"unknown_action_{args.action}"}

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
