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
    ("POST", "/api/admin/keys/rotate", {"service": "typesafe", "new_key": "tsk_rotated_zzzzzzzz9999"}),
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
        resp = client.request(method, path, json=body) if body is not None else client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} expected 401, got {resp.status_code}: {resp.text[:200]}"
    finally:
        if saved is not None:
            os.environ["ADMIN_API_KEY"] = saved
        else:
            os.environ.pop("ADMIN_API_KEY", None)


@pytest.mark.parametrize("method,path,body", MUTATION_AND_READ_ROUTES)
def test_wrong_api_key_rejected(client, keys_dir, method, path, body):
    _mount_ok()
    headers = {"X-API-Key": "wrong-key"}
    resp = client.request(
        method, path, json=body, headers=headers
    ) if body is not None else client.request(method, path, headers=headers)
    assert resp.status_code == 401, f"{method} {path} expected 401 with wrong key, got {resp.status_code}"


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
    assert resp.status_code == 503, f"expected 503 fail-closed, got {resp.status_code}: {resp.text[:200]}"
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
    decrypted = f.decrypt(value[len("fm1:"):]).decode()
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
    (keys_dir / "keys.json").write_text(json.dumps({"typesafe": {"value": "tsk_old_plaintext_key"}}))
    resp = client.get(
        "/api/admin/keys/redacted/typesafe",
        headers={"X-API-Key": "test-admin-key-xyz"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["storage"] == "legacy_plaintext"
    assert body["rotation_required"] is True
