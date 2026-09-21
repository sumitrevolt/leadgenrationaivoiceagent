"""Key Manager P0 hardening — storage/encryption behaviour tests.

Pins the enforced guarantees (see module docstring of app/platform/key_manager.py):
- Fernet encrypted at rest; no plaintext value in store OR audit
- fail-closed mutation without KEYS_MASTER_KEY
- legacy plaintext keys.json migrated once, verified, then securely deleted
- atomic .env deploy with backup, in-place update (no duplicate lines)
- owner-gated router: 401 anonymous / 403 admin-on-mutation / 200 super
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth_deps import get_current_user
from app.models.user import UserRole
from app.platform.key_manager import (
    KeyManagerAgent,
    KeyManagerError,
    build_keys_router,
    get_key_manager,
)

FAKE_KEY = "sk-test-leadgen-abcdef123456"


# -------------------------------------------------------------------------- #
# fixtures
# -------------------------------------------------------------------------- #


@pytest.fixture()
def km_env(tmp_path, monkeypatch):
    """Isolated keys dir + fresh master key + isolated runtime .env."""
    monkeypatch.setenv("LEADGEN_KEYS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("KEYS_MASTER_KEY", Fernet.generate_key().decode())
    (tmp_path / "secrets").mkdir()
    env_file = tmp_path / "runtime.env"
    env_file.write_text("OTHER=1\n", encoding="utf-8")
    monkeypatch.setenv("LEADGEN_ENV_FILE", str(env_file))
    yield tmp_path


@pytest.fixture()
def agent(km_env) -> KeyManagerAgent:
    return KeyManagerAgent()


def _user(role: UserRole) -> SimpleNamespace:
    """Minimal admin-lookalike user (no DB needed for router tests)."""
    return SimpleNamespace(
        role=role,
        can_access_admin=lambda: role in (UserRole.SUPER_ADMIN, UserRole.ADMIN),
    )


def _mini_app(agent: KeyManagerAgent, role: UserRole | None) -> FastAPI:
    app = FastAPI()
    app.include_router(build_keys_router())
    app.dependency_overrides[get_key_manager] = lambda: agent
    if role is not None:
        app.dependency_overrides[get_current_user] = lambda: _user(role)
    return app


def _enc_file(tmp: Path) -> Path:
    return tmp / "secrets" / "keys.enc.json"


# -------------------------------------------------------------------------- #
# storage behaviour
# -------------------------------------------------------------------------- #


def test_set_key_encrypted_at_rest(agent, km_env):
    res = agent.set_key("typesafe_a", FAKE_KEY, actor="owner")
    assert res["success"] is True
    assert res["state"] == "PRESENT"

    raw = _enc_file(km_env).read_text(encoding="utf-8")
    assert FAKE_KEY not in raw  # no plaintext anywhere in the store
    assert "cipher" in json.loads(raw)["typesafe_a"]

    # value surface roundtrip
    assert agent.get_decrypted_value("typesafe_a", consumer="typesafe-gateway") == FAKE_KEY
    assert agent.get_decrypted_value("nope", consumer="x") is None


def test_fail_closed_without_master(km_env, monkeypatch):
    monkeypatch.delenv("KEYS_MASTER_KEY", raising=False)
    agent = KeyManagerAgent()
    with pytest.raises(KeyManagerError) as ei:
        agent.set_key("typesafe_a", "kx12345678")
    assert ei.value.reason == "master_key_missing"
    # nothing written in plaintext
    assert not _enc_file(km_env).exists()


def test_invalid_service_name_rejected(agent):
    with pytest.raises(KeyManagerError) as ei:
        agent.set_key("UPPER CASE!", "kx12345678")
    assert ei.value.reason == "invalid_service_name"


def test_key_too_short_rejected(agent):
    with pytest.raises(KeyManagerError) as ei:
        agent.set_key("typesafe_a", "tiny")
    assert ei.value.reason == "key_too_short"


def test_no_prefix_or_value_leak_in_state_or_audit(agent, km_env):
    agent.set_key("typesafe_b", FAKE_KEY, actor="owner")
    state = agent.get_state("typesafe_b")
    dumped = json.dumps(state)
    assert FAKE_KEY not in dumped
    assert FAKE_KEY[:8] not in dumped  # no prefix exposure
    assert FAKE_KEY[-4:] not in dumped  # no suffix exposure
    assert state["state"] == "PRESENT"

    audit = (km_env / "secrets" / "audit.log").read_text(encoding="utf-8")
    assert FAKE_KEY not in audit
    assert FAKE_KEY[:8] not in audit


def test_legacy_plaintext_migration(agent, km_env):
    """Legacy keys.json (old plaintext impl) -> encrypted + plaintext removed."""
    secrets_dir = km_env / "secrets"
    legacy = secrets_dir / "keys.json"
    legacy.write_text(
        json.dumps({"legacy_svc": {"value": "old-secret-value-123"}}),
        encoding="utf-8",
    )
    assert agent.get_decrypted_value("legacy_svc", consumer="test") == "old-secret-value-123"
    assert not legacy.exists()  # plaintext copy destroyed after verified encrypt
    assert _enc_file(km_env).exists()


def test_deploy_to_env_atomic_update_and_backup(agent, km_env):
    env_file = km_env / "runtime.env"
    agent.set_key("typesafe_c", FAKE_KEY, actor="owner")
    res = agent.deploy_to_env("typesafe_c")
    assert res["success"] is True
    content = env_file.read_text(encoding="utf-8")
    assert "OTHER=1" in content  # existing lines preserved
    assert f"TYPESAFE_C_API_KEY={FAKE_KEY}" in content
    assert (km_env / "runtime.env.bak").exists()  # 0600 backup

    # update in place — exactly one line for the var, new value
    agent.set_key("typesafe_c", "sk-second-value-9876", actor="owner")
    agent.deploy_to_env("typesafe_c")
    content = env_file.read_text(encoding="utf-8")
    assert content.count("TYPESAFE_C_API_KEY=") == 1
    assert "TYPESAFE_C_API_KEY=sk-second-value-9876" in content


def test_deploy_without_key_fails_cleanly(agent, km_env):
    res = agent.deploy_to_env("typesafe_d")
    assert res["success"] is False
    assert res["reason"] == "no_key"


# -------------------------------------------------------------------------- #
# router wiring (owner-gated auth) on a minimal app
# -------------------------------------------------------------------------- #


def test_http_anonymous_rejected_401(km_env, agent):
    app = _mini_app(agent, role=None)
    client = TestClient(app)
    assert client.post(
        "/api/admin/keys/set", json={"service": "typesafe_a", "key": FAKE_KEY}
    ).status_code == 401
    assert client.get("/api/admin/keys/status").status_code == 401
    assert client.get("/api/admin/keys/audit").status_code == 401


def test_http_admin_cannot_mutate_403(km_env, agent):
    app = _mini_app(agent, role=UserRole.ADMIN)
    client = TestClient(app)
    r = client.post(
        "/api/admin/keys/set", json={"service": "typesafe_a", "key": FAKE_KEY}
    )
    assert r.status_code == 403  # mutation = super_admin only
    # but admin reads are allowed
    assert client.get("/api/admin/keys/status/typesafe_a").status_code == 200


def test_http_super_admin_can_set_200(km_env, agent):
    app = _mini_app(agent, role=UserRole.SUPER_ADMIN)
    client = TestClient(app)
    r = client.post(
        "/api/admin/keys/set", json={"service": "typesafe_a", "key": FAKE_KEY}
    )
    assert r.status_code == 200, r.text
    raw = _enc_file(km_env).read_text(encoding="utf-8")
    assert FAKE_KEY not in raw


def test_http_missing_master_key_503(km_env, agent, monkeypatch):
    monkeypatch.delenv("KEYS_MASTER_KEY", raising=False)
    app = _mini_app(agent, role=UserRole.SUPER_ADMIN)
    client = TestClient(app)
    r = client.post(
        "/api/admin/keys/set", json={"service": "typesafe_a", "key": FAKE_KEY}
    )
    assert r.status_code == 503
    assert "master_key_missing" in r.json()["detail"]
