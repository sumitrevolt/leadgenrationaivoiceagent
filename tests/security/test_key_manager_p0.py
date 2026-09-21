"""P0 lock-in: /api/admin/keys/* (app/platform/key_manager.py) must be owner-only
and never persist keys in plaintext.

Owner instruction R3 / R6 (2026-09-21): the router previously exposed
set/rotate/deploy with ZERO auth and stored literal key values in keys.json.
These tests lock the hardened contract:

1. Every route 401 without a valid ADMIN_API_KEY (X-API-Key header).
2. Wrong API key -> 401.
3. Without KEYS_MASTER_KEY, /set and /rotate FAIL CLOSED with 503
   (no plaintext write).
4. With a valid Fernet KEYS_MASTER_KEY, the stored file contains the
   ciphertext, never the raw key.
5. Responses expose no key prefix/fingerprint — only redacted slot state.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.platform.key_manager as km_mod
from app.main import app
from tests._api_helpers import iter_mounted_routes

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_auth_overrides() -> None:
    """Run the real owner gate (require_api_key) — no dependency overrides."""
    from app.api.auth_deps import (
        get_current_user,
        require_admin,
        require_agent,
        require_manager,
        require_super_admin,
    )

    for dependency in (
        get_current_user,
        require_admin,
        require_agent,
        require_manager,
        require_super_admin,
    ):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture
def keys_dir(tmp_path, monkeypatch):
    """Point the KeyManager at a throwaway dir (module constants + singleton)."""
    monkeypatch.setattr(km_mod, "KEYS_FILE", tmp_path / "keys.json")
    monkeypatch.setattr(km_mod, "AUDIT_LOG", tmp_path / "audit.log")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key-xyz")
    monkeypatch.delenv("KEYS_MASTER_KEY", raising=False)
    km_mod._key_manager = None
    yield tmp_path
    km_mod._key_manager = None


def _mount_ok() -> None:
    paths = [r.path for r in iter_mounted_routes(app)]
    assert "/api/admin/keys/set" in paths, (
        "key_manager router not mounted on app.main — P0 tests would 404; "
        "check the guarded mount block in app/main.py"
    )


MUTATION_AND_READ_ROUTES = [
    ("POST", "/api/admin/keys/set", {"service": "typesafe", "key": "tsk_live_abcdefgh12345678"}),
    (
        "POST",
        "/api/admin/keys/rotate",
        {"service": "typesafe", "new_key": "tsk_rotated_zzzzzzzz9999"},
    ),
    ("POST", "/api/admin/keys/deploy/typesafe", None),
    ("GET", "/api/admin/keys/status/typesafe", None),
    ("GET", "/api/admin/keys/redacted/typesafe", None),
    ("GET", "/api/admin/keys/audit/typesafe", None),
    ("GET", "/api/admin/keys/audit", None),
]


# ---------------------------------------------------------------------------
# 1+2. Owner-only auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", MUTATION_AND_READ_ROUTES)
def test_unauthenticated_rejected(client, keys_dir, method, path, body):
    _mount_ok()
    import os

    # Strip the admin key so the gate must fail-closed with 401.
    saved = os.environ.get("ADMIN_API_KEY")
    os.environ.pop("ADMIN_API_KEY", None)
    try:
        resp = (
            client.request(method, path, json=body)
            if body is not None
            else client.request(method, path)
        )
        assert resp.status_code == 401, (
            f"{method} {path} expected 401, got {resp.status_code}: {resp.text[:200]}"
        )
    finally:
        if saved is not None:
            os.environ["ADMIN_API_KEY"] = saved
        else:
            os.environ.pop("ADMIN_API_KEY", None)


@pytest.mark.parametrize("method,path,body", MUTATION_AND_READ_ROUTES)
def test_wrong_api_key_rejected(client, keys_dir, method, path, body):
    _mount_ok()
    headers = {"X-API-Key": "wrong-key"}
    resp = (
        client.request(method, path, json=body, headers=headers)
        if body is not None
        else client.request(method, path, headers=headers)
    )
    assert resp.status_code == 401, (
        f"{method} {path} expected 401 with wrong key, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 3. Fail-closed plaintext protection
# ---------------------------------------------------------------------------


def test_set_fails_closed_without_master_key(client, keys_dir):
    """No KEYS_MASTER_KEY -> /set must refuse to persist plaintext (503)."""
    _mount_ok()
    resp = client.post(
        "/api/admin/keys/set",
        json={"service": "typesafe", "key": "tsk_live_abcdefgh12345678"},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 503, (
        f"expected 503 fail-closed, got {resp.status_code}: {resp.text[:200]}"
    )
    keys_file = keys_dir / "keys.json"
    if keys_file.exists():
        content = keys_file.read_text()
        assert "tsk_live_abcdefgh12345678" not in content, "raw key leaked into keys.json"
    else:
        assert not keys_file.exists() or json.loads(keys_file.read_text() or "{}") == {}


# ---------------------------------------------------------------------------
# 4. Encrypted at rest with valid Fernet master key
# ---------------------------------------------------------------------------


def test_set_stores_ciphertext_not_plaintext(client, keys_dir, monkeypatch):
    _mount_ok()
    from cryptography.fernet import Fernet

    master = Fernet.generate_key()
    monkeypatch.setenv("KEYS_MASTER_KEY", master.decode())

    raw_key = "tsk_secret_value_000111222333"
    resp = client.post(
        "/api/admin/keys/set",
        json={"service": "typesafe", "key": raw_key},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 200, resp.text[:300]
    assert resp.json()["stored"] == "encrypted"

    stored = json.loads((keys_dir / "keys.json").read_text())
    value = stored["typesafe"]["value"]
    assert raw_key not in value, "raw key found in ciphertext slot — encryption not applied"
    assert value.startswith("fm1:"), "encrypted marker missing"
    # Round-trip proves the ciphertext is decryptable with the master key.
    f = Fernet(master)
    decrypted = f.decrypt(value[len("fm1:") :]).decode()
    assert decrypted == raw_key


# ---------------------------------------------------------------------------
# 5. No prefix/fingerprint leakage in owner-visible responses
# ---------------------------------------------------------------------------


def test_redacted_response_exposes_no_key_material(client, keys_dir, monkeypatch):
    _mount_ok()
    from cryptography.fernet import Fernet

    monkeypatch.setenv("KEYS_MASTER_KEY", Fernet.generate_key().decode())
    raw_key = "tsk_secret_value_000111222333"
    client.post(
        "/api/admin/keys/set",
        json={"service": "typesafe", "key": raw_key},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    resp = client.get(
        "/api/admin/keys/redacted/typesafe",
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["key_slot"] == "typesafe"
    assert body["storage"] == "encrypted"
    assert body["rotation_required"] is False
    text = resp.text
    for fragment in ("tsk_secret", "000111", raw_key[:8], raw_key[-4:]):
        assert fragment not in text, f"key fragment {fragment!r} leaked in response"


def test_legacy_plaintext_entry_flagged_rotation_required(client, keys_dir):
    """Pre-existing plaintext entry must surface ROTATION_REQUIRED, not be hidden."""
    _mount_ok()
    (keys_dir / "keys.json").write_text(
        json.dumps({"typesafe": {"value": "tsk_old_plaintext_key"}})
    )
    resp = client.get(
        "/api/admin/keys/redacted/typesafe",
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["storage"] == "legacy_plaintext"
    assert body["rotation_required"] is True


# ---------------------------------------------------------------------------
# 6. Regression locks from independent review (Cody/Tessa, 2026-09-21)
# ---------------------------------------------------------------------------


def test_rotate_fails_closed_without_master_key(client, keys_dir):
    """Rotate must fail closed too — not just set."""
    _mount_ok()
    # Seed an existing entry so rotate reaches the write path (not an early 404).
    (keys_dir / "keys.json").write_text(json.dumps({"typesafe": {"value": "fm1:seeded"}}))
    resp = client.post(
        "/api/admin/keys/rotate",
        json={"service": "typesafe", "new_key": "tsk_rotated_value_87654321"},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 503, f"rotate must fail closed, got {resp.status_code}"


def test_invalid_master_key_fails_closed(client, keys_dir, monkeypatch):
    """A malformed KEYS_MASTER_KEY must NOT fall back to plaintext storage."""
    _mount_ok()
    monkeypatch.setenv("KEYS_MASTER_KEY", "not-a-valid-fernet-key")
    resp = client.post(
        "/api/admin/keys/set",
        json={"service": "typesafe", "key": "tsk_live_abcdefgh12345678"},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 503
    keys_file = keys_dir / "keys.json"
    if keys_file.exists():
        assert "tsk_live_abcdefgh12345678" not in keys_file.read_text()


def test_short_key_returns_400_not_500(client, keys_dir, monkeypatch):
    """A too-short key must be a clean 400, not an opaque 500."""
    _mount_ok()
    from cryptography.fernet import Fernet

    monkeypatch.setenv("KEYS_MASTER_KEY", Fernet.generate_key().decode())
    resp = client.post(
        "/api/admin/keys/set",
        json={"service": "typesafe", "key": "short"},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}"


def test_rotate_unknown_service_returns_404(client, keys_dir, monkeypatch):
    """Rotating a *valid but unstored* service must be a clean 404.

    Note: the name must be env-var-safe (``[A-Za-z][A-Za-z0-9_]*``). A name with
    hyphens like ``does-not-exist`` is rejected earlier with 400 — it could never
    produce a valid ``<SERVICE>_API_KEY`` env var.
    """
    _mount_ok()
    from cryptography.fernet import Fernet

    monkeypatch.setenv("KEYS_MASTER_KEY", Fernet.generate_key().decode())
    resp = client.post(
        "/api/admin/keys/rotate",
        json={"service": "unknown_service", "new_key": "tsk_rotated_zzzzzzzz9999"},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}"


@pytest.mark.parametrize(
    "bad_service",
    [
        "FOO.*",  # regex wildcard — the original py/regex-injection vector
        "a)$",  # regex anchor / group close
        "svc; rm -rf /",  # shell metacharacters
        "a b",  # whitespace
        "../escape",  # path traversal attempt
        "1starts_with_digit",  # invalid env var name
        "",  # empty
        "x" * 65,  # over length cap
    ],
    ids=[
        "regex-wildcard",
        "regex-anchor",
        "shell-metachars",
        "whitespace",
        "path-traversal",
        "leading-digit",
        "empty",
        "too-long",
    ],
)
def test_invalid_service_name_returns_400(client, keys_dir, monkeypatch, bad_service):
    """CodeQL py/regex-injection regression: a service name that is not a safe
    env-var identifier must be rejected with 400 before it reaches any
    regex/env-write path. Never 500, never a silent write."""
    _mount_ok()
    from cryptography.fernet import Fernet

    monkeypatch.setenv("KEYS_MASTER_KEY", Fernet.generate_key().decode())
    resp = client.post(
        "/api/admin/keys/set",
        json={"service": bad_service, "key": "tsk_abcdefghijklmnop1234"},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 400, (
        f"service={bad_service!r} should be 400, got {resp.status_code}: {resp.text[:200]}"
    )


def test_validate_service_name_accepts_real_names():
    """The canonical service names used by the platform must still pass."""
    from app.platform.key_manager import validate_service_name

    for ok in ["typesafe", "openai", "GOOGLE_MAPS", "a", "svc_1"]:
        assert validate_service_name(ok) == ok


def test_deploy_env_replacement_is_literal_not_regex(monkeypatch, tmp_path):
    """Regression for the second half of the CodeQL finding: the old
    ``re.sub(pattern, f"{env_var}={plain}", ...)`` treated backslashes in the
    key value as backreference escapes. The replacement must be literal."""
    from app.platform import key_manager as km

    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=1\nMYAPP_API_KEY=old\n")

    monkeypatch.setattr(km, "KEYS_DIR", tmp_path)
    monkeypatch.setattr(km, "KEYS_FILE", tmp_path / "keys.json")
    monkeypatch.setattr(km, "AUDIT_LOG", tmp_path / "audit.log")

    from cryptography.fernet import Fernet

    monkeypatch.setenv("KEYS_MASTER_KEY", Fernet.generate_key().decode())

    kmgr = km.KeyManagerAgent()
    # A value containing regex-replacement metacharacters. Under the old
    # re.sub() this raised "invalid group reference" or wrote a mangled value.
    weird = r"tok\g<1>en\\with\backslashes"
    kmgr.set_key("myapp", weird)

    # Point the hardcoded deployment target at our temp file.
    from pathlib import Path as RealPath

    monkeypatch.setattr(
        km,
        "Path",
        lambda p: env_file if str(p) == "/opt/leadgen/.env" else RealPath(p),
    )

    res = kmgr.deploy_to_env("myapp")
    assert res.get("success") is True, res

    written = env_file.read_text()
    assert f"MYAPP_API_KEY={weird}" in written, written
    assert "EXISTING=1" in written, written
    assert "MYAPP_API_KEY=old" not in written, written


def test_audit_log_contains_no_key_material(client, keys_dir, monkeypatch):
    """The audit trail must never carry a key fragment (prefix or suffix)."""
    _mount_ok()
    from cryptography.fernet import Fernet

    monkeypatch.setenv("KEYS_MASTER_KEY", Fernet.generate_key().decode())
    raw = "tsk_audit_probe_555666777888"
    client.post(
        "/api/admin/keys/set",
        json={"service": "typesafe", "key": raw},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    audit = keys_dir / "audit.log"
    assert audit.exists(), "audit log was not written"
    text = audit.read_text()
    for frag in (raw, raw[:8], raw[-4:]):
        assert frag not in text, f"key fragment {frag!r} leaked into the audit log"


def test_legacy_entry_is_reencrypted_on_rotate(client, keys_dir, monkeypatch):
    """Rotating a legacy plaintext entry must migrate it to ciphertext."""
    _mount_ok()
    from cryptography.fernet import Fernet

    (keys_dir / "keys.json").write_text(
        json.dumps({"typesafe": {"value": "tsk_old_plaintext_value"}})
    )
    master = Fernet.generate_key()
    monkeypatch.setenv("KEYS_MASTER_KEY", master.decode())

    resp = client.post(
        "/api/admin/keys/rotate",
        json={"service": "typesafe", "new_key": "tsk_new_encrypted_value_9999"},
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 200, resp.text
    stored = json.loads((keys_dir / "keys.json").read_text())["typesafe"]["value"]
    assert stored.startswith("fm1:"), "legacy entry was not migrated to ciphertext"
    decrypted = Fernet(master).decrypt(stored[len("fm1:") :]).decode()
    assert decrypted == "tsk_new_encrypted_value_9999"
