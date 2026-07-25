"""OpenClaw Owner Copilot — auth, lanes, allowlist, Owner OS authority, trust boundary."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.auth_deps import (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_super_admin,
)
from app.integrations.openclaw import commands as oc_cmd
from app.integrations.openclaw import policies
from app.integrations.openclaw.auth import (
    CopilotActor,
    gateway_source_allowed,
    peer_host,
    require_copilot_actor,
    validate_gateway_token,
)
from app.integrations.openclaw.owner_os_adapter import _IDEMPOTENCY
from app.main import app
from app.models.user import UserRole
from app.platform import owner_os
from app.platform import owner_os_store as store
from tests.conftest import create_mock_user

client = TestClient(app)

# Auth deps this module may temporarily remove — never wipe unrelated overrides.
_AUTH_DEPS = (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_super_admin,
    require_copilot_actor,
)


@pytest.fixture(autouse=True)
def _openclaw_restore_global_state():
    """Snapshot/restore dependency overrides + OpenClaw idempotency only."""
    before = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(before)
    _IDEMPOTENCY.clear()


def _enable(monkeypatch, allowlist: str | None = None):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_ALLOW_RED_ACTIONS", "0")
    monkeypatch.setenv("OPENCLAW_REQUIRE_APPROVAL_FOR_AMBER", "1")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("OPENCLAW_GATEWAY_ALLOWED_IPS", "127.0.0.1,::1,testclient")
    # Leave CI-like ENVIRONMENT alone unless a test sets production markers.
    if allowlist is not None:
        monkeypatch.setenv("OPENCLAW_ALLOWED_COMMANDS", allowlist)
    else:
        monkeypatch.delenv("OPENCLAW_ALLOWED_COMMANDS", raising=False)
    _IDEMPOTENCY.clear()

    async def _admin_actor():
        return CopilotActor(
            id="test-admin",
            kind="admin",
            email="test@example.com",
            role="super_admin",
        )

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


def _snapshot_auth_overrides() -> dict:
    return {
        dep: app.dependency_overrides[dep] for dep in _AUTH_DEPS if dep in app.dependency_overrides
    }


def _clear_auth_overrides() -> dict:
    """Temporarily remove auth overrides; return snapshot for restore."""
    saved = _snapshot_auth_overrides()
    for dep in _AUTH_DEPS:
        app.dependency_overrides.pop(dep, None)
    return saved


def _restore_auth_overrides(saved: dict) -> None:
    for dep in _AUTH_DEPS:
        app.dependency_overrides.pop(dep, None)
    app.dependency_overrides.update(saved)


def _err_text(resp) -> str:
    body = resp.json()
    detail = body.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("error") or detail)
    if detail:
        return str(detail)
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)
    return str(body)


def _fake_request(host: str, headers: dict[str, str] | None = None) -> Request:
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/owner-copilot/command",
        "raw_path": b"/api/owner-copilot/command",
        "query_string": b"",
        "headers": hdrs,
        "client": (host, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Existing regression suite
# ---------------------------------------------------------------------------


def test_status_works_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "0")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)

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
    _clear_auth_overrides()
    r = client.get("/api/owner-copilot/status")
    assert r.status_code in (401, 403)


def test_gateway_token_auth(monkeypatch, tmp_path):
    _patch_owner_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_ALLOW_RED_ACTIONS", "0")
    monkeypatch.setenv("OPENCLAW_API_TOKEN", "local-dev-gateway-token-xyz")
    monkeypatch.setenv("OPENCLAW_GATEWAY_ALLOWED_IPS", "127.0.0.1,::1")
    monkeypatch.delenv("OPENCLAW_ALLOWED_COMMANDS", raising=False)
    # TestClient peer host varies by httpx/starlette — unit-test IP separately.
    monkeypatch.setattr(
        "app.integrations.openclaw.auth.gateway_source_allowed",
        lambda _req: True,
    )
    _IDEMPOTENCY.clear()
    _clear_auth_overrides()

    async def _no_user():
        return None

    app.dependency_overrides[get_current_user_optional] = _no_user
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


def test_customer_role_denied(monkeypatch):
    _enable(monkeypatch)

    async def _deny_actor():
        raise HTTPException(status_code=403, detail="Super admin access required")

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


@pytest.mark.parametrize(
    "phrase",
    [
        "Enable calling",
        "enable calling",
        "enable calls",
        "start calling",
        "calling enable",
        "Call chalu karo",
    ],
)
def test_calling_enable_phrase_matrix_is_red(phrase, monkeypatch, tmp_path):
    """Word-order / synonym gaps must not downgrade calling enable to GREEN."""
    from app.integrations.openclaw.commands import classify_nl

    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)
    proposal = classify_nl(phrase)
    assert proposal["safety_lane"] == "RED", phrase
    assert proposal["command"] == "calling.enable", phrase
    r = client.post(
        "/api/owner-copilot/nl",
        json={"text": phrase, "execute": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert (body.get("proposal") or {}).get("safety_lane") == "RED", phrase
    assert (body.get("proposal") or {}).get("command") == "calling.enable", phrase


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


def test_amber_confirm_true_still_parks(monkeypatch, tmp_path):
    """Admin UI sends confirm=true on Run — must park AMBER, never silent mutate."""
    _enable(
        monkeypatch,
        allowlist="platform.status,agent.pause,agents.list",
    )
    _patch_owner_stores(monkeypatch, tmp_path)
    r = client.post(
        "/api/owner-copilot/nl",
        json={
            "text": "Pause Isha safely",
            "execute": True,
            "confirm": True,
            "idempotency_key": "oc-pause-confirm-true",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert (body.get("proposal") or {}).get("safety_lane") == "AMBER"
    executed = body.get("executed") or {}
    assert executed.get("safety_lane") == "AMBER"
    assert executed.get("status") == "APPROVAL_REQUIRED"
    assert executed.get("approval_required") is True
    assert executed.get("ok") is True


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
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
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


def test_admin_dashboard_openclaw_panel_present():
    """Admin Console hosts OpenClaw panel wired to Owner Copilot APIs (not office/ask)."""
    r = client.get("/app/admin")
    assert r.status_code == 200
    assert 'id="openclawAdminCard"' in r.text
    assert "OpenClaw Copilot" in r.text
    assert "/api/owner-copilot/nl" in r.text
    assert "/api/owner-copilot/status" in r.text
    assert "/api/admin/owner-os/approvals" in r.text
    assert "/api/admin/owner-os/audit" in r.text
    assert "Owner OS = sole authority" in r.text
    # Enter (no Shift) → ocRun; Shift+Enter keeps newline in #ocText
    assert 'id="ocText"' in r.text
    assert 'e.key!=="Enter"' in r.text
    assert "window.ocRun()" in r.text
    # Office chat card remains separate — OpenClaw must not replace it with office/ask.
    assert 'id="agentCopilotCard"' in r.text
    assert r.text.index("openclawAdminCard") != r.text.index("agentCopilotCard")


def test_daily_brief(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)
    r = client.get("/api/owner-copilot/daily-brief")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["command"] == "business.daily_summary"


# ---------------------------------------------------------------------------
# Trust-boundary hardening
# ---------------------------------------------------------------------------


def test_human_customer_jwt_denied(monkeypatch):
    """Customer-like (viewer) JWT → 403 (not super-admin)."""
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    _clear_auth_overrides()
    customer = create_mock_user(user_id="cust-1", email="cust@x.com", role=UserRole.VIEWER)

    async def _cust():
        return customer

    app.dependency_overrides[get_current_user_optional] = _cust
    try:
        r = client.post("/api/owner-copilot/command", json={"command": "platform.status"})
        assert r.status_code == 403
        assert "Super admin" in _err_text(r)
    finally:
        _clear_auth_overrides()


def test_human_normal_admin_denied(monkeypatch):
    """Normal admin without SUPER_ADMIN → 403."""
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    _clear_auth_overrides()
    admin = create_mock_user(user_id="adm-1", email="admin@x.com", role=UserRole.ADMIN)

    async def _adm():
        return admin

    app.dependency_overrides[get_current_user_optional] = _adm
    try:
        r = client.post("/api/owner-copilot/command", json={"command": "platform.status"})
        assert r.status_code == 403
    finally:
        _clear_auth_overrides()


def test_human_module_rbac_denied(monkeypatch):
    """Module-RBAC grant must not become Owner Copilot authority."""
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    _clear_auth_overrides()
    agent = create_mock_user(user_id="ag-1", email="agent@x.com", role=UserRole.AGENT)
    # Pretend can_access_admin false but rbac would pass — role gate must still deny.
    agent.can_access_admin = MagicMock(return_value=False)  # type: ignore[method-assign]

    async def _ag():
        return agent

    app.dependency_overrides[get_current_user_optional] = _ag
    try:
        r = client.post("/api/owner-copilot/command", json={"command": "platform.status"})
        assert r.status_code == 403
    finally:
        _clear_auth_overrides()


def test_human_super_admin_accepted(monkeypatch, tmp_path):
    _patch_owner_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.delenv("OPENCLAW_ALLOWED_COMMANDS", raising=False)
    _IDEMPOTENCY.clear()
    _clear_auth_overrides()
    sa = create_mock_user(user_id="sa-1", email="sa@x.com", role=UserRole.SUPER_ADMIN)

    async def _sa():
        return sa

    app.dependency_overrides[get_current_user_optional] = _sa
    try:
        r = client.post(
            "/api/owner-copilot/command",
            json={"command": "platform.status", "idempotency_key": "sa-ok-1"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
    finally:
        _clear_auth_overrides()


def test_gateway_valid_token_allowlisted_ip(monkeypatch):
    monkeypatch.setenv("OPENCLAW_API_TOKEN", "gw-secret-token-aaaa")
    monkeypatch.setenv("OPENCLAW_GATEWAY_ALLOWED_IPS", "127.0.0.1,::1")
    assert validate_gateway_token("gw-secret-token-aaaa") is True
    req = _fake_request("127.0.0.1")
    assert gateway_source_allowed(req) is True


def test_gateway_valid_token_untrusted_ip_rejected(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_API_TOKEN", "gw-secret-token-bbbb")
    monkeypatch.setenv("OPENCLAW_GATEWAY_ALLOWED_IPS", "127.0.0.1,::1")
    _IDEMPOTENCY.clear()
    _clear_auth_overrides()
    # Force socket peer check to fail regardless of TestClient host.
    monkeypatch.setattr(
        "app.integrations.openclaw.auth.gateway_source_allowed",
        lambda _req: False,
    )

    async def _no_user():
        return None

    app.dependency_overrides[get_current_user_optional] = _no_user
    try:
        r = client.post(
            "/api/owner-copilot/command",
            json={"command": "platform.status"},
            headers={"Authorization": "Bearer gw-secret-token-bbbb"},  # nosecret
        )
        assert r.status_code == 403
        assert "allowlisted" in _err_text(r).lower()
    finally:
        _clear_auth_overrides()


def test_gateway_invalid_token_rejected(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_API_TOKEN", "gw-secret-token-cccc")
    monkeypatch.setenv("OPENCLAW_GATEWAY_ALLOWED_IPS", "testclient")
    _clear_auth_overrides()

    async def _no_user():
        return None

    app.dependency_overrides[get_current_user_optional] = _no_user
    try:
        r = client.post(
            "/api/owner-copilot/command",
            json={"command": "platform.status"},
            headers={"Authorization": "Bearer wrong-token"},  # nosecret
        )
        assert r.status_code == 401
    finally:
        _clear_auth_overrides()


def test_gateway_missing_token_rejected(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_API_TOKEN", "gw-secret-token-dddd")
    monkeypatch.setenv("OPENCLAW_GATEWAY_ALLOWED_IPS", "testclient")
    _clear_auth_overrides()

    async def _no_user():
        return None

    app.dependency_overrides[get_current_user_optional] = _no_user
    try:
        r = client.post("/api/owner-copilot/command", json={"command": "platform.status"})
        assert r.status_code == 401
    finally:
        _clear_auth_overrides()


def test_gateway_token_unset_fails_closed_for_anonymous(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    _clear_auth_overrides()

    async def _no_user():
        return None

    app.dependency_overrides[get_current_user_optional] = _no_user
    try:
        r = client.post(
            "/api/owner-copilot/command",
            json={"command": "platform.status"},
            headers={"Authorization": "Bearer anything"},  # nosecret
        )
        assert r.status_code == 401
    finally:
        _clear_auth_overrides()


def test_xff_spoof_does_not_bypass_source_check(monkeypatch):
    """Spoofed X-Forwarded-For: 127.0.0.1 must not override socket peer."""
    monkeypatch.setenv("OPENCLAW_GATEWAY_ALLOWED_IPS", "127.0.0.1,::1")
    req = _fake_request(
        "203.0.113.50",
        headers={"x-forwarded-for": "127.0.0.1", "x-real-ip": "127.0.0.1"},
    )
    assert peer_host(req) == "203.0.113.50"
    assert gateway_source_allowed(req) is False


def test_gateway_empty_allowlist_fails_closed(monkeypatch):
    monkeypatch.setenv("OPENCLAW_GATEWAY_ALLOWED_IPS", "")
    req = _fake_request("127.0.0.1")
    assert gateway_source_allowed(req) is False


def test_delivery_missing_tenant_rejected(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)
    r = client.post(
        "/api/owner-copilot/command",
        json={"command": "delivery.status", "params": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILED"
    assert body.get("error") == "tenant_id required"
    assert "jiya" not in str(body).lower()


def test_delivery_unknown_tenant_rejected(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)

    def _none(_cid):
        return None

    monkeypatch.setattr("app.marketing.clients_store.resolve_client", _none)
    r = client.post(
        "/api/owner-copilot/command",
        json={"command": "delivery.status", "params": {"tenant_id": "no-such-tenant-xyz"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILED"
    assert body.get("error") == "unknown tenant"


def test_delivery_canonical_tenant_accepted(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)

    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        lambda cid: {"id": "demo-tenant"} if cid == "demo-tenant" else None,
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.canonical_client_id",
        lambda cid: "demo-tenant",
    )
    monkeypatch.setattr(
        owner_os,
        "_build_status_report",
        lambda tid: {"tenant_id": tid, "ok": True},
    )
    r = client.post(
        "/api/owner-copilot/command",
        json={"command": "delivery.status", "params": {"tenant_id": "demo-tenant"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SUCCEEDED"
    assert (body.get("result") or {}).get("tenant_id") == "demo-tenant"


def test_delivery_billing_alias_resolves(monkeypatch, tmp_path):
    _enable(monkeypatch)
    _patch_owner_stores(monkeypatch, tmp_path)

    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        # nosecret — synthetic billing alias fixture, not a live credential
        lambda cid: (
            {"id": "jiya-makeover"} if cid in ("billing-alias-demo", "jiya-makeover") else None
        ),
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.canonical_client_id",
        lambda cid: "jiya-makeover",
    )
    monkeypatch.setattr(
        owner_os,
        "_build_status_report",
        lambda tid: {"tenant_id": tid, "ok": True},
    )
    r = client.post(
        "/api/owner-copilot/command",
        json={"command": "delivery.status", "params": {"client_id": "billing-alias-demo"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SUCCEEDED"
    assert (body.get("result") or {}).get("tenant_id") == "jiya-makeover"
    assert (body.get("result") or {}).get("requested_tenant") == "billing-alias-demo"


def test_no_default_jiya_in_handler():
    out = oc_cmd._delivery_status({}, actor="t", correlation_id="c1")
    assert out["status"] == "FAILED"
    assert out["error"] == "tenant_id required"


@pytest.mark.parametrize(
    "environment,app_env,expected",
    [
        ("development", "test", False),
        ("development", "production", True),
        ("production", "test", True),
        ("production", "development", True),
        ("production", "production", True),
        ("", "", False),
        ("staging", "staging", False),
        ("development", "", False),
        ("", "development", False),
    ],
)
def test_is_production_env_matrix(monkeypatch, environment, app_env, expected):
    """Any authoritative marker == production → production (CI ENVIRONMENT must not mask)."""
    if environment:
        monkeypatch.setenv("ENVIRONMENT", environment)
    else:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    if app_env:
        monkeypatch.setenv("APP_ENV", app_env)
    else:
        monkeypatch.delenv("APP_ENV", raising=False)
    assert policies.is_production_env() is expected


def _force_ci_like_production(monkeypatch):
    """Simulate GitHub Actions: ENVIRONMENT=development while APP_ENV=production under test."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("APP_ENV", "production")


def test_production_green_allowlist_accepted(monkeypatch):
    _force_ci_like_production(monkeypatch)
    monkeypatch.setenv(
        "OPENCLAW_ALLOWED_COMMANDS",
        "platform.status,agents.list",
    )
    monkeypatch.setattr(policies, "durable_idempotency_ready", lambda: False)
    allowed = policies.allowed_commands()
    assert allowed == frozenset({"platform.status", "agents.list"})


def test_production_amber_allowlist_stripped(monkeypatch):
    _force_ci_like_production(monkeypatch)
    monkeypatch.setenv(
        "OPENCLAW_ALLOWED_COMMANDS",
        "platform.status,agent.pause,agents.list",
    )
    monkeypatch.setattr(policies, "durable_idempotency_ready", lambda: False)
    allowed = policies.allowed_commands()
    assert "agent.pause" not in allowed
    assert "platform.status" in allowed
    assert allowed <= policies.GREEN_COMMANDS


def test_red_rejected_even_with_allow_red_flag(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_ALLOW_RED_ACTIONS", "1")
    monkeypatch.setenv(
        "OPENCLAW_ALLOWED_COMMANDS",
        "platform.status,calling.enable,shell.execute",
    )
    ok, reason = policies.command_permitted("calling.enable")
    assert ok is False
    assert "RED" in reason
    assert "calling.enable" not in policies.allowed_commands()


def test_stage_a_cannot_mutate_agent_state_in_production(monkeypatch):
    monkeypatch.setenv("OPENCLAW_ENABLED", "1")
    _force_ci_like_production(monkeypatch)
    monkeypatch.setenv(
        "OPENCLAW_ALLOWED_COMMANDS",
        "platform.status,agent.pause,agent.resume",
    )
    monkeypatch.setattr(policies, "durable_idempotency_ready", lambda: False)
    ok, reason = policies.command_permitted("agent.pause")
    assert ok is False
    assert "AMBER" in reason or "OPENCLAW_ALLOWED_COMMANDS" in reason or "durable" in reason
