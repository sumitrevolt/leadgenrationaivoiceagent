"""Per-tool scoped HMAC for Coordination Hub inbound adapters.

Secrets live only in env (COORD_HUB_TOOL_<ID>_SECRET / COORD_HUB_BUZZ_SECRET).
Signatures never grant Owner OS admin, deploy, dial, or mission-mutation access.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any

ATTESTATION_VERSION = "coord-hub-hmac-sha256-v1"
SECRET_MIN_CHARS = 32
MAX_PAST_AGE_SECONDS = 300
MAX_FUTURE_SKEW_SECONDS = 30

_KNOWN_TOOLS = ("cursor", "claude", "monkeycode", "opencode", "bolt", "buzz", "hermes")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

_HUB_ROOT = "data/coordination_hub"
_NONCE_FILE = "data/coordination_hub/nonce_fps.jsonl"
_MAX_NONCE_LINES = 5000


def hub_enabled() -> bool:
    return os.getenv("COORDINATION_HUB_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _secret_env_name(tool_id: str) -> str:
    tid = str(tool_id or "").strip().lower()
    if tid == "buzz":
        return "COORD_HUB_BUZZ_SECRET"
    return f"COORD_HUB_TOOL_{tid.upper()}_SECRET"


def _configured_secret(tool_id: str) -> str:
    name = _secret_env_name(tool_id)
    secret = os.getenv(name, "").strip() if name else ""
    return secret if len(secret) >= SECRET_MIN_CHARS else ""


def tool_auth_status() -> dict[str, Any]:
    """Booleans only — never return secret names' values or fingerprints."""
    configured: dict[str, bool] = {}
    for tid in _KNOWN_TOOLS:
        configured[tid] = bool(_configured_secret(tid))
    return {
        "attestation_version": ATTESTATION_VERSION,
        "tools_configured": configured,
        "required_secret_min_chars": SECRET_MIN_CHARS,
        "known_tools": list(_KNOWN_TOOLS),
    }


def nonce_fingerprint(nonce: str) -> str:
    return hashlib.sha256(str(nonce).encode("utf-8")).hexdigest()


def _canonical_payload(
    *,
    tool_id: str,
    event_type: str,
    body_sha256: str,
    issued_at: int,
    nonce: str,
) -> bytes:
    payload = {
        "body_sha256": str(body_sha256).strip().lower(),
        "event_type": str(event_type).strip().lower(),
        "issued_at": int(issued_at),
        "nonce": str(nonce),
        "tool_id": str(tool_id).strip().lower(),
        "version": ATTESTATION_VERSION,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def body_sha256(raw: bytes | str) -> str:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_tool_signature(
    *,
    secret: str,
    tool_id: str,
    event_type: str,
    body_sha256: str,
    issued_at: int,
    nonce: str,
) -> str:
    payload = _canonical_payload(
        tool_id=tool_id,
        event_type=event_type,
        body_sha256=body_sha256,
        issued_at=issued_at,
        nonce=nonce,
    )
    return hmac.new(str(secret).encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _nonce_seen(fp: str) -> bool:
    if not os.path.isfile(_NONCE_FILE):
        return False
    try:
        with open(_NONCE_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(row.get("fp") or "") == fp:
                    return True
    except OSError:
        return False
    return False


def _record_nonce(fp: str) -> None:
    os.makedirs(_HUB_ROOT, exist_ok=True)
    with open(_NONCE_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"fp": fp, "at": int(time.time())}, separators=(",", ":")) + "\n")
    try:
        with open(_NONCE_FILE, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        if len(lines) > _MAX_NONCE_LINES:
            keep = lines[-_MAX_NONCE_LINES:]
            with open(_NONCE_FILE, "w", encoding="utf-8") as fh:
                fh.write("\n".join(keep) + "\n")
    except OSError:
        pass


def verify_tool_attestation(
    *,
    tool_id: str,
    event_type: str,
    body: bytes | str,
    issued_at: str | int | None,
    nonce: str | None,
    signature: str | None,
    now: int | None = None,
    consume_nonce: bool = True,
) -> dict[str, Any]:
    """Fail-closed HMAC verify with timestamp skew + nonce replay protection."""
    tid = str(tool_id or "").strip().lower()
    et = str(event_type or "").strip().lower()
    nonce_s = str(nonce or "")
    sig = str(signature or "").strip().lower()
    digest = body_sha256(body)

    if not _TOOL_RE.fullmatch(tid) or tid not in _KNOWN_TOOLS:
        return {"ok": False, "reason": "tool_unknown", "version": ATTESTATION_VERSION}
    secret = _configured_secret(tid)
    if not secret:
        return {"ok": False, "reason": "secret_unconfigured", "version": ATTESTATION_VERSION}
    try:
        issued_at_int = int(str(issued_at))
    except (TypeError, ValueError):
        return {"ok": False, "reason": "attestation_malformed", "version": ATTESTATION_VERSION}
    if (
        not et
        or not _NONCE_RE.fullmatch(nonce_s)
        or not _SHA256_RE.fullmatch(sig)
        or not _SHA256_RE.fullmatch(digest)
    ):
        return {"ok": False, "reason": "attestation_malformed", "version": ATTESTATION_VERSION}

    current = int(time.time()) if now is None else int(now)
    if (
        issued_at_int < current - MAX_PAST_AGE_SECONDS
        or issued_at_int > current + MAX_FUTURE_SKEW_SECONDS
    ):
        return {"ok": False, "reason": "timestamp_outside_window", "version": ATTESTATION_VERSION}

    expected = build_tool_signature(
        secret=secret,
        tool_id=tid,
        event_type=et,
        body_sha256=digest,
        issued_at=issued_at_int,
        nonce=nonce_s,
    )
    if not hmac.compare_digest(expected, sig):
        return {"ok": False, "reason": "signature_invalid", "version": ATTESTATION_VERSION}

    fp = nonce_fingerprint(nonce_s)
    if _nonce_seen(fp):
        return {"ok": False, "reason": "nonce_replay", "version": ATTESTATION_VERSION}
    if consume_nonce:
        _record_nonce(fp)
    return {
        "ok": True,
        "reason": "verified",
        "version": ATTESTATION_VERSION,
        "nonce_fp": fp,
        "body_sha256": digest,
    }


def build_configured_tool_headers(
    *,
    tool_id: str,
    event_type: str,
    body: bytes | str,
    issued_at: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Test/helper: build headers without returning the env secret."""
    secret = _configured_secret(tool_id)
    if not secret:
        raise ValueError("tool_secret_unconfigured")
    timestamp = int(time.time()) if issued_at is None else int(issued_at)
    nonce_value = nonce or secrets.token_urlsafe(24)
    if not _NONCE_RE.fullmatch(nonce_value):
        raise ValueError("attestation_nonce_invalid")
    digest = body_sha256(body)
    signature = build_tool_signature(
        secret=secret,
        tool_id=tool_id,
        event_type=event_type,
        body_sha256=digest,
        issued_at=timestamp,
        nonce=nonce_value,
    )
    return {
        "X-CoordHub-Timestamp": str(timestamp),
        "X-CoordHub-Nonce": nonce_value,
        "X-CoordHub-Signature": signature,
        "X-CoordHub-Event-Type": str(event_type).strip().lower(),
    }


__all__ = [
    "ATTESTATION_VERSION",
    "SECRET_MIN_CHARS",
    "hub_enabled",
    "tool_auth_status",
    "nonce_fingerprint",
    "body_sha256",
    "build_tool_signature",
    "verify_tool_attestation",
    "build_configured_tool_headers",
]
