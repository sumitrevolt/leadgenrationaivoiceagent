"""Stdlib TOTP (RFC 6238) — 2FA bina kisi dep ke. ADMIN_TOTP_SECRET env se gate hota."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_secret(length: int = 20) -> str:
    """Random base32 TOTP secret (RFC 4648, unpadded). length=20 bytes → 160-bit, 32 chars."""
    return base64.b32encode(secrets.token_bytes(length)).decode().rstrip("=")


def provisioning_uri(
    secret_b32: str, account: str, issuer: str = "LeadsGenAI", digits: int = 6, step: int = 30
) -> str:
    """otpauth:// URI for authenticator apps (Google Authenticator, Authy, etc.)."""
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={digits}&period={step}"
    )


def _code(secret_b32: str, counter: int, digits: int = 6) -> str:
    s = (secret_b32 or "").strip().replace(" ", "").upper()
    key = base64.b32decode(s + "=" * (-len(s) % 8))
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 15
    return str((struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF) % 10**digits).zfill(digits)


def totp_now(secret_b32: str, step: int = 30) -> str:
    return _code(secret_b32, int(time.time() // step))


def verify_totp(secret_b32: str, code: str, window: int = 1, step: int = 30) -> bool:
    """±window steps tolerance (clock skew). Never raises — bad input = False."""
    try:
        code = (code or "").strip()
        if not code:
            return False
        now = int(time.time() // step)
        return any(
            hmac.compare_digest(_code(secret_b32, now + w), code)
            for w in range(-window, window + 1)
        )
    except Exception:
        return False
