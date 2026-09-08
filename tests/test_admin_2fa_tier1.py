"""Tier-1 Slice D — regression tests for per-user admin 2FA (TOTP).

Covers secret encryption round-trip, enroll→activate, TOTP + single-use recovery-code
login verification, recovery regeneration, disable, preferences preservation, and the
policy/enforcement helpers. Uses a fake User object (no DB) and a fixed TOTP_ENC_KEY so
encryption is deterministic.
"""

import asyncio
import json

import pytest

from app.platform import admin_2fa
from app.utils import totp


@pytest.fixture(autouse=True)
def _enc_key(monkeypatch):
    # deterministic Fernet key so encrypt/decrypt works without app settings
    monkeypatch.setenv("TOTP_ENC_KEY", "unit-test-totp-key")
    monkeypatch.delenv("ADMIN_2FA_ENFORCE", raising=False)


class _FakeUser:
    def __init__(self, prefs=None, role="ADMIN"):
        from app.models.user import UserRole

        self.id = "u1"
        self.email = "admin@example.com"
        self.is_2fa_enabled = False
        self.preferences = json.dumps(prefs) if prefs else None
        self.role = getattr(UserRole, role)


def _prefs_dict(user):
    return json.loads(user.preferences) if user.preferences else {}


# ---- encryption ---------------------------------------------------------------


def test_encrypt_decrypt_round_trip():
    tok = admin_2fa.encrypt_secret("JBSWY3DPEHPK3PXP")
    assert tok != "JBSWY3DPEHPK3PXP"  # ciphertext, not plaintext
    assert admin_2fa.decrypt_secret(tok) == "JBSWY3DPEHPK3PXP"
    assert admin_2fa.decrypt_secret("garbage") is None


# ---- enrollment → activation --------------------------------------------------


def test_enroll_returns_secret_and_codes_but_not_enabled():
    u = _FakeUser()
    enroll = admin_2fa.generate_enrollment(u)
    assert enroll["secret"] and enroll["otpauth_uri"].startswith("otpauth://totp/")
    assert len(enroll["recovery_codes"]) == 10
    assert u.is_2fa_enabled is False  # not enabled until activate
    tf = _prefs_dict(u)["twofa"]
    assert "pending_enc" in tf and "secret_enc" not in tf
    # raw secret is NOT stored anywhere in plaintext
    assert enroll["secret"] not in json.dumps(_prefs_dict(u))


def test_activate_with_valid_code_enables():
    u = _FakeUser()
    enroll = admin_2fa.generate_enrollment(u)
    code = totp.totp_now(enroll["secret"])
    assert admin_2fa.activate(u, code) is True
    assert u.is_2fa_enabled is True
    assert admin_2fa.is_enabled(u) is True
    tf = _prefs_dict(u)["twofa"]
    assert "secret_enc" in tf and "pending_enc" not in tf


def test_activate_with_wrong_code_fails():
    u = _FakeUser()
    admin_2fa.generate_enrollment(u)
    assert admin_2fa.activate(u, "000000") is False
    assert u.is_2fa_enabled is False


# ---- login verification (TOTP + recovery) -------------------------------------


def _enable(u):
    enroll = admin_2fa.generate_enrollment(u)
    admin_2fa.activate(u, totp.totp_now(enroll["secret"]))
    return enroll


def test_login_verify_totp():
    u = _FakeUser()
    enroll = _enable(u)
    code = totp.totp_now(enroll["secret"])
    assert asyncio.run(admin_2fa.verify_login_code(u, code)) is True
    assert asyncio.run(admin_2fa.verify_login_code(u, "000000")) is False


def test_recovery_code_is_single_use():
    u = _FakeUser()
    enroll = _enable(u)
    rc = enroll["recovery_codes"][0]
    assert asyncio.run(admin_2fa.verify_login_code(u, rc)) is True
    # same code cannot be reused
    assert asyncio.run(admin_2fa.verify_login_code(u, rc)) is False
    # a different, unused code still works
    assert asyncio.run(admin_2fa.verify_login_code(u, enroll["recovery_codes"][1])) is True


def test_regenerate_recovery_invalidates_old():
    u = _FakeUser()
    enroll = _enable(u)
    old = enroll["recovery_codes"][2]
    new_codes = admin_2fa.regenerate_recovery(u)
    assert old not in new_codes
    assert asyncio.run(admin_2fa.verify_login_code(u, old)) is False
    assert asyncio.run(admin_2fa.verify_login_code(u, new_codes[0])) is True


# ---- disable + preferences preservation ---------------------------------------


def test_disable_clears_2fa():
    u = _FakeUser()
    _enable(u)
    admin_2fa.disable(u)
    assert u.is_2fa_enabled is False
    assert admin_2fa.is_enabled(u) is False
    assert "twofa" not in _prefs_dict(u)


def test_enrollment_preserves_other_preferences():
    u = _FakeUser(prefs={"rbac_grants": ["clients"], "theme": "dark"})
    admin_2fa.generate_enrollment(u)
    p = _prefs_dict(u)
    assert p["rbac_grants"] == ["clients"]  # untouched
    assert p["theme"] == "dark"
    assert "twofa" in p


# ---- policy / enforcement -----------------------------------------------------


def test_enforcement_and_must_setup(monkeypatch):
    u = _FakeUser(role="ADMIN")
    assert admin_2fa.role_mandatory(u) is True
    # enforcement off → no forced setup
    assert admin_2fa.must_setup(u) is False
    monkeypatch.setenv("ADMIN_2FA_ENFORCE", "1")
    assert admin_2fa.must_setup(u) is True  # mandatory role, not enrolled
    _enable(u)
    assert admin_2fa.must_setup(u) is False  # enrolled → satisfied


def test_viewer_not_mandatory():
    u = _FakeUser(role="VIEWER")
    assert admin_2fa.role_mandatory(u) is False
