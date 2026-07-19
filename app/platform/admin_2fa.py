"""Tier-1 Slice D — per-user admin 2FA (TOTP) with encrypted secrets + recovery codes.

Replaces the single shared ``ADMIN_TOTP_SECRET`` with per-user TOTP. MIGRATION-FREE:
the ``users.two_fa_secret`` column is only String(32) (too small for a ciphertext), so
the encrypted secret, recovery-code hashes, pending-enrollment state and metadata all
live under a ``twofa`` key in the existing ``users.preferences`` JSON (Text). Other
preferences keys (e.g. rbac grants) are preserved.

Security properties:
  * Secret is encrypted at rest with Fernet (key = ``TOTP_ENC_KEY`` if set, else derived
    from the app JWT secret). The raw secret is returned exactly once, at enrollment.
  * Recovery codes are stored only as salted SHA-256 hashes and are single-use.
  * ``ADMIN_TOTP_SECRET`` remains a bootstrap / break-glass fallback so the owner cannot
    be permanently locked out.
  * Enforcement is policy-gated (``ADMIN_2FA_ENFORCE``) and bootstrap-safe: a mandatory
    user who hasn't enrolled is flagged ``must_setup`` rather than hard-locked.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any

logger = logging.getLogger(__name__)

_ISSUER = os.getenv("ADMIN_2FA_ISSUER", "LeadsGenAI")
_RECOVERY_COUNT = 10
_PENDING_TTL = 15 * 60  # a started-but-unconfirmed enrollment expires in 15 min


# --------------------------------------------------------------------------- crypto
def _fernet():
    from cryptography.fernet import Fernet

    key_env = os.getenv("TOTP_ENC_KEY")
    if key_env:
        raw = key_env.encode()
    else:
        from app.config import settings

        raw = ("totp2fa:" + str(settings.jwt_secret_key)).encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:
        return None


def _hash_code(code: str) -> str:
    return hashlib.sha256(
        ("rc:" + (code or "").strip().lower().replace("-", "")).encode()
    ).hexdigest()


# --------------------------------------------------------------------------- prefs I/O
def _prefs(user) -> dict:
    p = getattr(user, "preferences", None)
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            p = {}
    return dict(p or {})


def _save_prefs(user, prefs: dict) -> None:
    # preferences is a Text column holding JSON.
    user.preferences = json.dumps(prefs)


def _twofa(user) -> dict:
    return dict(_prefs(user).get("twofa") or {})


def _save_twofa(user, tf: dict) -> None:
    prefs = _prefs(user)
    prefs["twofa"] = tf
    _save_prefs(user, prefs)


# --------------------------------------------------------------------------- state
def user_has_secret(user) -> bool:
    return bool(_twofa(user).get("secret_enc"))


def is_enabled(user) -> bool:
    return bool(getattr(user, "is_2fa_enabled", False)) and user_has_secret(user)


# --------------------------------------------------------------------------- enrollment
def generate_enrollment(user) -> dict:
    """Create a PENDING secret + recovery codes. Returns the otpauth URI, the raw secret
    and the plaintext recovery codes ONCE. Does not enable 2FA (call activate() next)."""
    from app.utils.totp import generate_secret, provisioning_uri

    secret = generate_secret()
    codes = [
        "-".join((c[:5], c[5:])) for c in (secrets.token_hex(5) for _ in range(_RECOVERY_COUNT))
    ]
    tf = _twofa(user)
    tf["pending_enc"] = encrypt_secret(secret)
    tf["pending_ts"] = int(time.time())
    tf["recovery"] = [_hash_code(c) for c in codes]
    _save_twofa(user, tf)
    return {
        "otpauth_uri": provisioning_uri(secret, account=user.email, issuer=_ISSUER),
        "secret": secret,
        "recovery_codes": codes,
    }


def activate(user, code: str) -> bool:
    """Confirm a pending enrollment with a TOTP code → enable 2FA."""
    from app.utils.totp import verify_totp

    tf = _twofa(user)
    pend = tf.get("pending_enc")
    ts = int(tf.get("pending_ts") or 0)
    if not pend or (time.time() - ts) > _PENDING_TTL:
        return False
    secret = decrypt_secret(pend)
    if not secret or not verify_totp(secret, code):
        return False
    tf["secret_enc"] = pend
    tf.pop("pending_enc", None)
    tf.pop("pending_ts", None)
    tf["activated_at"] = int(time.time())
    _save_twofa(user, tf)
    user.is_2fa_enabled = True
    return True


async def verify_login_code(user, code: str) -> bool:
    """Verify a TOTP OR consume a single-use recovery code at login.

    Mutates ``user`` when a recovery code is consumed (caller must commit).
    """
    from app.utils.totp import verify_totp

    code = (code or "").strip()
    if not code:
        return False
    tf = _twofa(user)
    secret = decrypt_secret(tf.get("secret_enc"))
    if secret and verify_totp(secret, code):
        return True
    # recovery-code fallback (single use)
    h = _hash_code(code)
    rc = list(tf.get("recovery") or [])
    if h in rc:
        rc.remove(h)
        tf["recovery"] = rc
        _save_twofa(user, tf)
        logger.info(
            "admin_2fa: recovery code consumed user=%s remaining=%d",
            getattr(user, "id", "?"),
            len(rc),
        )
        return True
    return False


def regenerate_recovery(user) -> list[str]:
    """Issue a fresh set of recovery codes (invalidates old). Returns plaintext once."""
    codes = [
        "-".join((c[:5], c[5:])) for c in (secrets.token_hex(5) for _ in range(_RECOVERY_COUNT))
    ]
    tf = _twofa(user)
    tf["recovery"] = [_hash_code(c) for c in codes]
    _save_twofa(user, tf)
    return codes


def disable(user) -> None:
    """Fully remove 2FA for a user (secret + recovery + pending)."""
    prefs = _prefs(user)
    prefs.pop("twofa", None)
    _save_prefs(user, prefs)
    user.is_2fa_enabled = False


# --------------------------------------------------------------------------- policy
def enforcement_on() -> bool:
    return os.getenv("ADMIN_2FA_ENFORCE", "0") == "1"


def role_mandatory(user) -> bool:
    from app.models.user import UserRole

    role = getattr(user, "role", None)
    return role in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER)


def must_setup(user) -> bool:
    """True if policy requires this user to enroll 2FA but they haven't (bootstrap nudge)."""
    return enforcement_on() and role_mandatory(user) and not is_enabled(user)


def status(user) -> dict[str, Any]:
    tf = _twofa(user)
    return {
        "enabled": is_enabled(user),
        "mandatory": role_mandatory(user),
        "enforcement_on": enforcement_on(),
        "must_setup": must_setup(user),
        "recovery_remaining": len(tf.get("recovery") or []),
    }
