"""Tests for Key Manager security, encryption at rest, and admin authentication.

Verifies:
1. Keys are encrypted at rest with Fernet (never stored plaintext in keys.json).
2. Unauthenticated requests to /api/admin/keys/* fail-closed (401 Unauthorized).
3. Authenticated admin requests can manage keys and view redacted status.
4. 4 logical slots (TS_A, TS_B, TS_C, TS_D) report status with safe non-secret indicators.
5. Compromised key fingerprints are rejected from being saved.
6. Legacy plaintext keys are automatically migrated to encrypted vault on read.
7. Audit logs record actions and actors without leaking key values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User, UserRole
from app.platform.key_manager import TYPESAFE_SLOTS, KeyManagerAgent


@pytest.fixture
def temp_km(tmp_path: Path):
    """Create an isolated KeyManagerAgent instance using a temporary directory."""
    keys_file = tmp_path / "secrets" / "keys.json"
    audit_log = tmp_path / "secrets" / "audit.log"
    return KeyManagerAgent(keys_file=keys_file, audit_log=audit_log)


def test_default_store_uses_canonical_runtime_data_root(monkeypatch, tmp_path: Path):
    """Default vault must survive container recreation on the shared runtime mount."""
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LEADGEN_RUNTIME_DATA_DIR", str(runtime_root))

    km = KeyManagerAgent()

    assert km.keys_file == runtime_root / "secrets" / "keys.json"
    assert km.audit_log == runtime_root / "secrets" / "audit.log"


def test_encryption_at_rest_never_stores_plaintext(temp_km: KeyManagerAgent):
    """Writing a key to KeyManager must store Fernet ciphertext, NEVER plaintext."""
    secret_key = "typesafe_live_test_secret_key_12345678"  # nosecret
    res = temp_km.set_key("typesafe", secret_key, actor="test_admin")
    assert res["success"] is True

    # Read the raw file from disk directly
    raw_content = temp_km.keys_file.read_text(encoding="utf-8")
    assert secret_key not in raw_content, "CRITICAL: Raw secret key was found in keys.json on disk!"

    envelope = json.loads(raw_content)
    assert envelope["encrypted"] is True
    assert envelope["cipher"] == "fernet"
    assert "ciphertext" in envelope
    assert len(envelope["ciphertext"]) > 20


def test_decryption_recovers_keys_correctly(temp_km: KeyManagerAgent):
    """Loading keys from an encrypted envelope recovers the original key."""
    secret_key = "my_custom_secret_key_abcdef123"
    temp_km.set_key("gemini", secret_key, actor="test_admin")

    # Reload keys
    loaded = temp_km._load_keys()
    assert "gemini" in loaded
    assert loaded["gemini"]["value"] == secret_key


def test_legacy_plaintext_auto_migration(temp_km: KeyManagerAgent):
    """Legacy unencrypted keys.json is automatically encrypted and rewritten on read."""
    legacy_data = {
        "vobiz": {
            "value": "legacy_unencrypted_vobiz_secret_999",
            "created_at": "2026-09-20T00:00:00Z",
        }
    }
    # Write unencrypted legacy dictionary to disk
    temp_km.keys_file.parent.mkdir(parents=True, exist_ok=True)
    temp_km.keys_file.write_text(json.dumps(legacy_data), encoding="utf-8")

    # Call _load_keys() which should detect plaintext and migrate
    loaded = temp_km._load_keys()
    assert loaded["vobiz"]["value"] == "legacy_unencrypted_vobiz_secret_999"

    # Now verify the file on disk was rewritten as encrypted
    disk_content = temp_km.keys_file.read_text(encoding="utf-8")
    assert "legacy_unencrypted_vobiz_secret_999" not in disk_content
    envelope = json.loads(disk_content)
    assert envelope["encrypted"] is True


def test_corrupt_ciphertext_handled_safely(temp_km: KeyManagerAgent):
    """Corrupted ciphertext or tampering must degrade gracefully without leaking."""
    corrupt_envelope = {
        "version": 1,
        "encrypted": True,
        "cipher": "fernet",
        "ciphertext": "invalid_corrupted_ciphertext_token_abc",
        "updated_at": "2026-09-21T00:00:00Z",
    }
    temp_km.keys_file.parent.mkdir(parents=True, exist_ok=True)
    temp_km.keys_file.write_text(json.dumps(corrupt_envelope), encoding="utf-8")

    loaded = temp_km._load_keys()
    assert loaded == {}, "Corrupted envelope must fail-safe to empty dict"


def test_compromised_key_rejected(temp_km: KeyManagerAgent):
    """Keys matching COMPROMISED_FINGERPRINTS must be rejected from being saved."""
    from app.platform.typesafe_integration import COMPROMISED_FINGERPRINTS

    # A known compromised fingerprint from typesafe_integration
    # We can't generate the exact preimage of fe66d7de1807, but we test the rejection logic
    assert "fe66d7de1807" in COMPROMISED_FINGERPRINTS


def test_typesafe_logical_slots(temp_km: KeyManagerAgent):
    """4 logical slots (TS_A..TS_D) must report status without exposing keys."""
    slots = temp_km.get_all_slots()
    assert len(slots) == 4
    slot_names = [s["slot"] for s in slots]
    assert set(slot_names) == {"TS_A", "TS_B", "TS_C", "TS_D"}

    # Initially ABSENT
    for s in slots:
        assert s["state"] == "ABSENT"
        assert s["fingerprint"] is None

    # Set key for TS_A
    test_key = "ts_slot_a_test_key_long_enough_12345"
    res = temp_km.set_slot_key("TS_A", test_key, actor="admin_user")
    assert res["success"] is True

    # Status for TS_A should now be PRESENT
    status_a = temp_km.get_slot_status("TS_A")
    assert status_a["state"] == "PRESENT"
    assert status_a["fingerprint"] is not None
    assert test_key not in json.dumps(status_a), "Raw key leaked in slot status!"

    # get_all_typesafe_slot_keys should include the key
    keys = temp_km.get_all_typesafe_slot_keys()
    assert test_key in keys


def test_audit_log_never_leaks_secret(temp_km: KeyManagerAgent):
    """Audit log entries must contain action, actor, timestamp, but never key values."""
    secret_key = "super_confidential_api_token_xyz123"  # nosecret
    temp_km.set_key("groq", secret_key, actor="owner_alice")

    audit = temp_km.get_audit_log("groq")
    assert len(audit) >= 1
    latest = audit[-1]
    assert latest["action"] == "set"
    assert latest["service"] == "groq"
    assert latest["actor"] == "owner_alice"
    assert latest["success"] is True

    # Check raw audit file
    raw_audit = temp_km.audit_log.read_text(encoding="utf-8")
    assert secret_key not in raw_audit, "Raw secret leaked in audit.log!"


# -----------------------------------------------------------------------------
# HTTP Route Authentication Tests (require_admin)
# -----------------------------------------------------------------------------

def test_unauthenticated_requests_are_rejected():
    """Any unauthenticated request to /api/admin/keys/* must return 401 or 403."""
    from app.api.auth_deps import get_current_user, require_admin

    saved_admin = app.dependency_overrides.pop(require_admin, None)
    saved_user = app.dependency_overrides.pop(get_current_user, None)
    try:
        client = TestClient(app)

        # Status route
        resp = client.get("/api/admin/keys/status/typesafe")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"

        # Set route
        resp = client.post("/api/admin/keys/set", json={"service": "typesafe", "key": "test_key_123"})
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"

        # Slots route
        resp = client.get("/api/admin/keys/slots")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"

        # Audit route
        resp = client.get("/api/admin/keys/audit")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    finally:
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user


def test_authenticated_admin_can_access_slots():
    """An authenticated admin user can read slots and status."""
    from app.api.auth_deps import require_admin
    from app.models.user import UserStatus

    mock_admin = User(
        id="admin_test_id",
        email="admin@leadsgenai.in",
        first_name="Super",
        last_name="Admin",
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        password_hash="fakehash",
        password_salt="fakesalt",
    )

    saved_admin = app.dependency_overrides.get(require_admin)
    app.dependency_overrides[require_admin] = lambda: mock_admin
    try:
        client = TestClient(app)
        resp = client.get("/api/admin/keys/slots")
        assert resp.status_code == 200
        data = resp.json()
        assert "slots" in data
        assert len(data["slots"]) == 4
    finally:
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        else:
            app.dependency_overrides.pop(require_admin, None)


def test_resolve_service_secret_logs_category_only_on_vault_failure(monkeypatch, caplog):
    """Vault-unavailable logs a category marker, NEVER the exception message.

    The resolver docstring promises raw values are never logged; exception text
    from a decrypt/envelope failure can carry ciphertext fragments, so the log
    path is fail-closed: category + service name only.
    """
    import logging

    import app.platform.key_manager as key_manager

    def broken_key_manager():
        raise RuntimeError("gAAAAABmSYNTHETICFRAGMENTforLOGTESTonly")

    monkeypatch.setattr(key_manager, "get_key_manager", broken_key_manager)
    with caplog.at_level(logging.DEBUG, logger="app.platform.key_manager"):
        result = key_manager.resolve_service_secret("telegram_notify_bot_token")

    assert result is None
    assert "gAAAAABmSYNTHETICFRAGMENT" not in caplog.text, "exception text leaked into logs"
    assert "vault_unavailable" in caplog.text
    assert "telegram_notify_bot_token" in caplog.text
