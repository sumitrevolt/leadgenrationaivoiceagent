"""OpenClaw Owner Copilot — auth, lanes, allowlist, Owner OS authority."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.api.auth_deps import (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_super_admin,
)
from app.integrations.openclaw import commands as oc_cmd
from app.integrations.openclaw import policies
from app.integrations.openclaw.auth import require_copilot_actor
from app.integrations.openclaw.owner_os_adapter import _IDEMPOTENCY
from app.main import app
from app.platform import owner_os
from app.platform import owner_os_store as store

client = TestClient(app)


def _enable(monkeypatch, allowlist: str | None = None):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_ALLOW_RED_ACTIONS", "0")
    monkeypatch.setenv("OPENCLAW_REQUIRE_APPROVAL_FOR_AMBER", "1")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    if allowlist is not None:
        monkeypatch.setenv("OPENCLAW_ALLOWED_COMMANDS", allowlist)
    else:
        monkeypatch.delenv("OPENCLAW_ALLOWED_COMMANDS", raising=False)
    _IDEMPOTENCY.clear()
    # Ensure admin JWT path works under TestClient (optional-user override).
    from app.integrations.openclaw.auth import CopilotActor

    async def _admin_actor():
        return CopilotActor(id="test-admin", kind="admin", email="test@example.com")

    app.dependency_overrides[require_copilot_actor] = _admin_actor


def _patch_owner_stores(monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_OS_STORAGE", "jsonl")
    store.reset_storage_mode()
    monkeypatch.setattr(owner_os, "_CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(owner_os, "_KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(owner_os, "_AUDIT_STORE", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(store, "CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(store, "KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(store, "AUDIT_STORE", str(tmp_path / "audit.jsonl"))


def test_status_works_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "0")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    from app.integrations.openclaw.auth import CopilotActor

    async def _admin_actor():
        return CopilotActor(id="test-admin", kind="admin", email="test@example.com")

    app.dependency_overrides[require_copilot_actor] = _admin_actor
    r = client.get("/api/owner-copilot/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["calling_hard_off"] is True


def test_command_fails_closed_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "0")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    from app.integrations.openclaw.auth import CopilotActor

    async def _admin_actor():
        return CopilotActor(id="test-admin", kind="admin", email="test@example.com")

    app.dependency_overrides[require_copilot_actor] = _admin_actor
    r = client.post(
        "/api/owner-copilot/command",
        json={"command": "platform.status", "params": {}},
    )
    assert r.status_code == 503
    body = r.json()
    detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
    err = (detail or {}).get("error") or body.get("error")
    assert err == "openclaw_disabled" or "openclaw" in str(body).lower()


def test_unauthenticated_denied(monkeypatch):
    _enable(monkeypatch)
    saved = {
        require_admin: app.dependency_overrides.pop(require_admin, None),
        get_current_user: app.dependency_overrides.pop(get_current_user, None),
        get_current_user_optional: app.dependency_overrides.pop(get_current_user_optional, None),
        require_super_admin: app.dependency_overrides.pop(require_super_admin, None),
        require_copilot_actor: app.dependency_overrides.pop(require_copilot_actor, None),
    }
    try:
        r = client.get("/api/owner-copilot/status")
        assert r.status_code in (401, 403)
    finally:
        for dep, fn in saved.items():
            if fn is not None:
                app.dependency_overrides[dep] = fn


def test_gateway_token_auth(monkeypatch, tmp_path):
    _patch_owner_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_ALLOW_RED_ACTIONS", "0")
    monkeypatch.setenv("OPENCLAW_API_TOKEN", "local-dev-gateway-token-xyz")
    monkeypatch.delenv("OPENCLAW_ALLOWED_COMMANDS", raising=False)
    _IDEMPOTENCY.clear()
    # Clear JWT / actor overrides so only gateway token authenticates.
    saved = {
        get_current_user: app.dependency_overrides.pop(get_current_user, None),
        get_current_user_optional: app.dependency_overrides.pop(get_current_user_optional, None),
        require_admin: app.dependency_overrides.pop(require_admin, None),
        require_copilot_actor: app.dependency_overrides.pop(require_copilot_actor, None),
    }

    async def _no_user():
        return None

    app.dependency_overrides[get_current_user_optional] = _no_user
    try:
        _tok = "local-dev-gateway-token-xyz"
        bad = client.post(
            "/api/owner-copilot/command",
            json={"command": "platform.status"},
            headers={"Authorization": "Bearer wrong"},  # nosecret — fake auth negative path
        )
        assert bad.status_code == 401
        good = client.post(
            "/api/owner-copilot/command",
            json={"command": "platform.status", "idempotency_key": "gw-tok-1"},
            headers={"Authorization": f"Bearer {_tok}"},  # nosecret — local test double only
        )
        assert good.status_code == 200
        body = good.json()
        assert body["ok"] is True
        assert body["status"] == "SUCCEEDED"
    finally:
        for dep, fn in saved.items():
            if fn is not None:
                app.dependency_overrides[dep] = fn
            else:
                app.dependency_overrides.pop(dep, None)


def test_customer_role_denied(monkeypatch):
    _enable(monkeypatch)

    async def _deny_actor():
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Admin access required")

    saved = app.dependency_overrides.get(require_copilot_actor)
    app.dependency_overrides[require_copilot_actor] = _deny_actor
    try:
        r = client.post(
            "/api/owner-copilot/command",
            json={"command": "platform.status"},
        )
        assert r.status_code == 403
    finally:
        if saved is not None:
            app.dependency_overrides[require_copilot_actor] = saved
        else:
            app.dependency_overrides.pop(require_copilot_actor, None)


def test_platform_status_green(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)
    r = client.post(
        "/api/owner-copilot/command",
        json={"command": "platform.status", "idempotency_key": "oc-ps-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["safety_lane"] == "GREEN"
    assert body["status"] == "SUCCEEDED"
    assert body["verified"] is True
    assert (body.get("result") or {}).get("calling_badge")


def test_agents_list_31(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)
    r = client.post("/api/owner-copilot/command", json={"command": "agents.list"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    agents = (body.get("result") or {}).get("agents") or []
    assert len(agents) == 31
    assert (body.get("result") or {}).get("staff_count") == 31


def test_unknown_command_rejected(monkeypatch):
    _enable(monkeypatch)
    r = client.post(
        "/api/owner-copilot/command",
        json={"command": "shell.execute", "params": {"cmd": "ls"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["safety_lane"] == "RED"
    assert body["status"] == "REJECTED"


def test_sql_injection_chars_blocked(monkeypatch):
    _enable(monkeypatch)
    r = client.post(
        "/api/owner-copilot/command",
        json={"command": "platform.status; DROP TABLE users"},
    )
    assert r.status_code == 400


def test_red_calling_nl_rejected(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)
    r = client.post(
        "/api/owner-copilot/nl",
        json={"text": "platform_dial calling enable karo", "execute": True},
    )
    assert r.status_code == 200
    body = r.json()
    executed = body.get("executed") or {}
    assert executed.get("safety_lane") == "RED"
    assert executed.get("ok") is False
    assert executed.get("status") == "REJECTED"


def test_amber_pause_requires_approval(monkeypatch, tmp_path):
    _enable(
        monkeypatch,
        allowlist="platform.status,agent.pause,agents.list",
    )
    _patch_owner_stores(monkeypatch, tmp_path)
    r = client.post(
        "/api/owner-copilot/command",
        json={
            "command": "agent.pause",
            "params": {"agent_id": "isha"},
            "confirm": False,
            "idempotency_key": "oc-pause-1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["safety_lane"] == "AMBER"
    assert body["status"] == "APPROVAL_REQUIRED"
    assert body["approval_required"] is True
    assert body.get("command_id")


def test_idempotency_green(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)
    payload = {"command": "queues.status", "idempotency_key": "oc-q-dup"}
    r1 = client.post("/api/owner-copilot/command", json=payload)
    r2 = client.post("/api/owner-copilot/command", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json().get("deduped") is True


def test_non_allowlisted_denied(monkeypatch):
    _enable(monkeypatch, allowlist="platform.status")
    r = client.post("/api/owner-copilot/command", json={"command": "agents.list"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "OPENCLAW_ALLOWED_COMMANDS" in (body.get("error") or "")


def test_classify_ambiguous_is_readonly():
    prop = oc_cmd.classify_nl("kuch kar do jaldi")
    assert prop["command"] == "platform.status"
    assert prop["safety_lane"] == "GREEN"
    assert prop["confidence"] == "low"


def test_policy_red_never_in_allowlist(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv(
        "OPENCLAW_ALLOWED_COMMANDS",
        "platform.status,calling.enable,shell.execute",
    )
    allowed = policies.allowed_commands()
    assert "calling.enable" not in allowed
    assert "shell.execute" not in allowed
    assert "platform.status" in allowed


def test_owner_copilot_page_tab_present():
    r = client.get("/app/owner")
    assert r.status_code == 200
    assert "Owner Copilot" in r.text
    assert "OPENCLAW_ENABLED" in r.text


def test_daily_brief(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)
    r = client.get("/api/owner-copilot/daily-brief")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["command"] == "business.daily_summary"
