#!/usr/bin/env python3
"""Coordination Hub heartbeat — coding tools ko live presence bhejne ka primitive.

Koi bhi tool (opencode/cursor/claude/bolt/monkeycode) session start/end pe isse
call karke apni presence Coordination Hub dashboard (/app/coordination) me
update karta hai. HMAC-signed; secret env se aata hai — kabhi commit nahi.

Usage (bash / powershell, secret env me):
  COORD_HUB_TOOL_OPENCODE_SECRET=<secret> python scripts/coord_hub_heartbeat.py opencode

Optional env (meta tagging):
  COORD_HUB_BASE_URL   default https://leadsgenai.in
  COORD_HUB_BRANCH     git branch ya worktree label (dashboards me dikhta hai)
  COORD_HUB_WORKTREE   worktree name (dashboards me dikhta hai)

Signs with the SAME canonical payload the deployed backend verifies
(app/platform/coordination_hub_auth.py _canonical_payload) — 200 = verified.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

ATTESTATION_VERSION = "coord-hub-hmac-sha256-v1"
SECRET_MIN_CHARS = 32


def _canonical_payload(*, tool_id: str, body_sha256: str, issued_at: int, nonce: str) -> bytes:
    payload = {
        "body_sha256": body_sha256,
        "event_type": "heartbeat",
        "issued_at": int(issued_at),
        "nonce": nonce,
        "tool_id": tool_id,
        "version": ATTESTATION_VERSION,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _send(tool_id: str, secret: str, base: str) -> int:
    meta = {
        "branch": os.environ.get("COORD_HUB_BRANCH", ""),
        "worktree": os.environ.get("COORD_HUB_WORKTREE", ""),
        "host": os.environ.get("COORD_HUB_HOST", ""),
    }
    body = json.dumps(
        {"status": "online", "meta": {k: v for k, v in meta.items() if v}},
        separators=(",", ":"),
    ).encode("utf-8")

    issued_at = int(time.time())
    nonce = secrets.token_urlsafe(24)
    digest = hashlib.sha256(body).hexdigest()
    signature = hmac.new(
        secret.encode("utf-8"),
        _canonical_payload(tool_id=tool_id, body_sha256=digest, issued_at=issued_at, nonce=nonce),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-CoordHub-Timestamp": str(issued_at),
        "X-CoordHub-Nonce": nonce,
        "X-CoordHub-Signature": signature,
        "X-CoordHub-Event-Type": "heartbeat",
    }
    req = urllib.request.Request(
        f"{base}/api/admin/owner-os/coordination-hub/tools/{tool_id}/heartbeat",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
            text = resp.read().decode("utf-8", "replace")
            print(f"[coord-hub] {tool_id}: http={resp.status} {text[:160]}")
            return 0 if resp.status == 200 else 1
    except urllib.error.HTTPError as e:
        print(f"[coord-hub] {tool_id}: http={e.code} {e.read().decode('utf-8', 'replace')[:160]}")
        return 1
    except Exception as e:  # noqa: BLE001 - network fallback must not crash callers
        print(f"[coord-hub] {tool_id}: error {e}")
        return 1


def main() -> int:
    tool_id = (
        (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("COORD_HUB_TOOL", "opencode"))
        .strip()
        .lower()
    )
    if not tool_id or not tool_id.isalnum():
        print(f"[coord-hub] invalid tool_id: {tool_id!r}")
        return 2
    secret = os.environ.get(f"COORD_HUB_TOOL_{tool_id.upper()}_SECRET", "").strip()
    if len(secret) < SECRET_MIN_CHARS:
        # lgtm[py/clear-text-logging-sensitive-data] - static message; the secret value is never logged
        print("[coord-hub] ERROR: heartbeat key for tool is missing or too short - not sent.")
        return 2
    base = os.environ.get("COORD_HUB_BASE_URL", "https://leadsgenai.in").rstrip("/")
    return _send(tool_id=tool_id, secret=secret, base=base)


if __name__ == "__main__":
    sys.exit(main())
