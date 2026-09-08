"""customer_totp.py — TOTP-based 2FA for customer accounts.

Mirrors the admin TOTP pattern (`app/utils/totp.py` + `ADMIN_TOTP_SECRET`) but
opt-in per-customer. Customer enrols, scans an authenticator-app QR (from the
returned otpauth URI), confirms with the first code, and from that login
onwards the customer-login flow demands a TOTP code before issuing a JWT.

Design:
- **Storage**: data/customer_totp.jsonl, atomic rewrite on enrol/disable.
  One row per client_id: {client_id, secret, enabled_at, recovery_hashes[]}.
  Secrets are stored plain (the customer can already see them at enrol —
  not a meaningful incremental risk for a v1 self-hosted SaaS).
- **Recovery codes**: 8 single-use codes shown ONCE at enrol; stored as
  SHA-256 hashes; consumed on use. Customer can call /disable with either a
  fresh TOTP code OR a recovery code.
- **Pending-login challenge**: when login succeeds with email+password but
  2FA is enabled, the login endpoint returns a short-lived "challenge" token
  instead of a JWT. The customer POSTs that challenge + their TOTP code to
  /api/customer/2fa/verify to get the real JWT. Challenge tokens are HMAC-
  signed using TOTP_CHALLENGE_KEY (random per restart if unset) and expire
  after 5 minutes.
- **No new dependency**: reuses stdlib `app.utils.totp` for the math.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Optional

from app.utils.logger import setup_logger
from app.utils.totp import verify_totp as _verify_totp

logger = setup_logger(__name__)

_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_PATH = _DATA_DIR / "customer_totp.jsonl"

_ISSUER = "LeadsGenAI"
_CHALLENGE_TTL_S = 300
_RECOVERY_CODE_COUNT = 8


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _ensure_dir() -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _read_all() -> list[dict]:
    if not _PATH.exists():
        return []
    try:
        out: list[dict] = []
        for line in _PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


def _atomic_rewrite(rows: list[dict]) -> bool:
    _ensure_dir()
    tmp = _PATH.with_suffix(".jsonl.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(_PATH)
        return True
    except Exception as exc:
        logger.error("customer_totp rewrite failed: %s", exc)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _row(client_id: str) -> dict | None:
    cid = (client_id or "").strip()
    for r in _read_all():
        if r.get("client_id") == cid:
            return r
    return None


def _upsert(row: dict) -> bool:
    cid = row["client_id"]
    rows = _read_all()
    new = [r for r in rows if r.get("client_id") != cid]
    new.append(row)
    return _atomic_rewrite(new)


# --------------------------------------------------------------------------- #
# Public state checks
# --------------------------------------------------------------------------- #
def is_enabled(client_id: str) -> bool:
    """2FA armed for this customer? Used by the login flow gate."""
    return _row(client_id) is not None


# --------------------------------------------------------------------------- #
# Enrol / disable
# --------------------------------------------------------------------------- #
def _gen_secret() -> str:
    """160-bit base32 secret (RFC 4226 recommendation)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _gen_recovery_codes(n: int = _RECOVERY_CODE_COUNT) -> list[str]:
    """8 human-typable codes (XXXX-XXXX, base32 alphabet)."""
    out = []
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I/O/0/1 (typing fatigue)
    for _ in range(n):
        rng = secrets.SystemRandom()
        s = "".join(rng.choice(alphabet) for _ in range(8))
        out.append(f"{s[:4]}-{s[4:]}")
    return out


def _hash_recovery(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").upper().encode()).hexdigest()


def begin_enroll(client_id: str, email: str) -> dict:
    """Generate a fresh secret + recovery codes WITHOUT enabling yet. Customer
    must confirm with the first TOTP code via confirm_enroll() — until then no
    state is persisted (avoids leaving half-enrolled rows around)."""
    cid = (client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id required"}
    if is_enabled(cid):
        return {"ok": False, "error": "2fa already enabled — disable first"}
    secret = _gen_secret()
    recovery = _gen_recovery_codes()
    label = (email or cid).replace(" ", "")
    otpauth = f"otpauth://totp/{_ISSUER}:{label}?secret={secret}&issuer={_ISSUER}"
    return {
        "ok": True,
        "secret": secret,
        "otpauth_uri": otpauth,
        "recovery_codes": recovery,
        "issuer": _ISSUER,
    }


def confirm_enroll(client_id: str, secret: str, code: str, recovery_codes: list[str]) -> dict:
    """Customer scanned the QR and typed the first code from their app +
    saved their recovery codes — verify + persist. Both `secret` and
    `recovery_codes` came from begin_enroll(); the customer is the trust
    boundary that kept them between calls (they're shown once)."""
    cid = (client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id required"}
    if is_enabled(cid):
        return {"ok": False, "error": "2fa already enabled"}
    if not _verify_totp(secret, code):
        return {"ok": False, "error": "bad TOTP code — re-scan and try again"}
    row = {
        "client_id": cid,
        "secret": secret,
        "enabled_at": int(time.time()),
        "recovery_hashes": [_hash_recovery(c) for c in (recovery_codes or [])],
    }
    if not _upsert(row):
        return {"ok": False, "error": "storage write failed"}
    return {"ok": True, "enabled_at": row["enabled_at"]}


def disable(client_id: str, code_or_recovery: str) -> dict:
    """Disable 2FA. Either a current TOTP code OR a recovery code is required
    (so a customer who lost their authenticator app can still get out)."""
    cid = (client_id or "").strip()
    row = _row(cid)
    if not row:
        return {"ok": False, "error": "2fa not enabled"}
    code = (code_or_recovery or "").strip()
    if not code:
        return {"ok": False, "error": "code required"}

    accepted = False
    # Try TOTP first
    if len(code) == 6 and code.isdigit():
        accepted = _verify_totp(row["secret"], code)
    # Fall through to recovery code
    if not accepted:
        h = _hash_recovery(code)
        if h in (row.get("recovery_hashes") or []):
            accepted = True

    if not accepted:
        return {"ok": False, "error": "bad code"}

    rows = [r for r in _read_all() if r.get("client_id") != cid]
    _atomic_rewrite(rows)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Login challenge — short-lived signed token between password and TOTP step
# --------------------------------------------------------------------------- #
def _challenge_key() -> bytes:
    """HMAC key for the login challenge. Falls back to a per-process random
    key if TOTP_CHALLENGE_KEY isn't set (cluster-safe across single-VPS)."""
    k = os.environ.get("TOTP_CHALLENGE_KEY", "").strip()
    if not k:
        # Cache the random key for the process lifetime so a challenge issued
        # at t=0 still verifies at t=120 in the same process.
        global _RANDOM_KEY
        try:
            _ = _RANDOM_KEY
        except NameError:
            _RANDOM_KEY = secrets.token_hex(32)
        k = _RANDOM_KEY
    return k.encode("utf-8")


def create_challenge(client_id: str) -> str:
    """Issue a signed (client_id, expiry, nonce) blob. Customer posts this
    back with their TOTP code in /verify."""
    payload = {
        "cid": client_id,
        "exp": int(time.time()) + _CHALLENGE_TTL_S,
        "n": uuid.uuid4().hex[:12],
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(_challenge_key(), body, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(body).decode() + "." + sig


def consume_challenge(token: str) -> str | None:
    """Verify the challenge signature + expiry. Return client_id or None.
    NB: not actually single-use — verifying the TOTP code is what gates the
    JWT issuance, and TOTP codes are themselves single-use per step."""
    try:
        body_b64, sig = (token or "").split(".", 1)
        body = base64.urlsafe_b64decode(body_b64.encode() + b"==")
        expected = hmac.new(_challenge_key(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(body)
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return str(payload.get("cid"))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Verify (used by login flow + sensitive-action gate)
# --------------------------------------------------------------------------- #
def verify(client_id: str, code: str) -> bool:
    """Return True if `code` is a current TOTP OR an unused recovery code.
    Recovery codes are CONSUMED (removed from the row) on success."""
    row = _row(client_id)
    if not row:
        return False
    code = (code or "").strip().upper().replace("-", "")
    if not code:
        return False
    # TOTP
    if len(code) == 6 and code.isdigit():
        if _verify_totp(row["secret"], code):
            return True
    # Recovery code (consume)
    h = _hash_recovery(code)
    hashes = list(row.get("recovery_hashes") or [])
    if h in hashes:
        hashes.remove(h)
        row["recovery_hashes"] = hashes
        _upsert(row)
        return True
    return False


__all__ = [
    "is_enabled",
    "begin_enroll",
    "confirm_enroll",
    "disable",
    "create_challenge",
    "consume_challenge",
    "verify",
]
