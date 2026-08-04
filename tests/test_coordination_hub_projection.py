"""Hub is a thin Owner OS projection — inert when OFF; no second registry."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.platform import coordination_hub as hub
from app.platform import coordination_hub_auth as auth_mod
from app.platform import coordination_hub_events as events_mod
from app.platform.coordination_hub_auth import build_configured_tool_headers, hub_enabled

client = TestClient(app)


def _hub_tmp(monkeypatch, tmp_path):
    root = tmp_path / "coordination_hub"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(events_mod, "_ROOT", str(root))
    monkeypatch.setattr(events_mod, "_EVENTS", str(root / "events.jsonl"))
    monkeypatch.setattr(events_mod, "_PRESENCE", str(root / "presence.json"))
    monkeypatch.setattr(events_mod, "_PRESENCE_TMP", str(root / "presence.json.tmp"))
    monkeypatch.setattr(auth_mod, "_HUB_ROOT", str(root))
    monkeypatch.setattr(auth_mod, "_NONCE_FILE", str(root / "nonce_fps.jsonl"))


def test_hub_disabled_by_default(monkeypatch):
    monkeypatch.delenv("COORDINATION_HUB_ENABLED", raising=False)
    assert hub_enabled() is False
    snap = hub.snapshot(include_git=False)
    assert snap["ok"] is True
    assert snap["enabled"] is False
    assert snap["events_tail"] == []
    assert snap["mutations"] == "refused_use_owner_os_or_missions"


def test_mutation_refused_points_to_owner_os():
    out = hub.mutation_refused("pause_agent")
    assert out["ok"] is False
    assert out["error"] == "use_owner_os"
    assert out["hub"] == "projection_only"


def test_snapshot_enabled_projects_without_writing_staff(monkeypatch, tmp_path):
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "1")
    _hub_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(
        hub, "probe_git", lambda: {"ok": True, "head": "deadbeef", "redacted": True}
    )
    snap = hub.snapshot(include_git=True)
    assert snap["enabled"] is True
    assert snap["role"] == "owner_os_thin_projection"
    assert "owner_agents" in snap
    assert "missions" in snap
    assert snap["pointers"]["owner_os_ui"] == "/app/owner"


def test_heartbeat_rejects_admin_bearer_without_hmac(monkeypatch, tmp_path):
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "1")
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", "c" * 40)
    _hub_tmp(monkeypatch, tmp_path)
    r = client.post(
        "/api/admin/owner-os/coordination-hub/tools/cursor/heartbeat",
        headers={"Authorization": "Bearer fake-admin-jwt", "Content-Type": "application/json"},
        content=b'{"status":"online"}',
    )
    assert r.status_code == 401
    body = r.json()
    msg = body.get("detail") or (body.get("error") or {}).get("message") or ""
    assert msg == "hmac_required"


def test_heartbeat_hmac_ok(monkeypatch, tmp_path):
    secret = "c" * 40
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "1")
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", secret)
    _hub_tmp(monkeypatch, tmp_path)
    body = b'{"status":"online","meta":{"branch":"feat/x"}}'
    issued = 1_750_000_200
    headers = build_configured_tool_headers(
        tool_id="cursor",
        event_type="heartbeat",
        body=body,
        issued_at=issued,
        nonce="heartbeat_nonce_ok_01",
    )
    monkeypatch.setattr(auth_mod.time, "time", lambda: issued)
    r = client.post(
        "/api/admin/owner-os/coordination-hub/tools/cursor/heartbeat",
        headers={**headers, "Content-Type": "application/json"},
        content=body,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["auth"] == "hmac"
    assert data["tool_id"] == "cursor"


def test_buzz_webhook_hmac_and_replay(monkeypatch, tmp_path):
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "1")
    monkeypatch.setenv("COORD_HUB_BUZZ_SECRET", "b" * 40)
    _hub_tmp(monkeypatch, tmp_path)
    body = b'{"event_type":"note","channel":"#admin","summary":"ping"}'
    issued = 1_750_000_300
    headers = build_configured_tool_headers(
        tool_id="buzz",
        event_type="buzz_event",
        body=body,
        issued_at=issued,
        nonce="buzz_webhook_nonce_01",
    )
    monkeypatch.setattr(auth_mod.time, "time", lambda: issued)
    r1 = client.post(
        "/api/admin/owner-os/coordination-hub/webhooks/buzz",
        headers={**headers, "Content-Type": "application/json"},
        content=body,
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        "/api/admin/owner-os/coordination-hub/webhooks/buzz",
        headers={**headers, "Content-Type": "application/json"},
        content=body,
    )
    assert r2.status_code == 401
    body2 = r2.json()
    msg2 = body2.get("detail") or (body2.get("error") or {}).get("message") or ""
    assert msg2 == "nonce_replay"


def test_git_and_events_admin_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "1")
    _hub_tmp(monkeypatch, tmp_path)
    (tmp_path / "coordination_hub" / "events.jsonl").write_text(
        json.dumps({"ts": 1, "tool_id": "cursor", "event_type": "heartbeat"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.api.coordination_hub.probe_git",
        lambda: {"ok": True, "head": "abc", "redacted": True},
    )
    eg = client.get("/api/admin/owner-os/coordination-hub/events")
    assert eg.status_code == 200
    assert eg.json()["ok"] is True
    gg = client.get("/api/admin/owner-os/coordination-hub/git")
    assert gg.status_code == 200
    assert gg.json().get("redacted") is True


def test_inbound_404_when_flag_off(monkeypatch):
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "0")
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", "c" * 40)
    r = client.post(
        "/api/admin/owner-os/coordination-hub/tools/cursor/heartbeat",
        content=b"{}",
    )
    assert r.status_code == 404


def test_owner_os_page_has_hub_tab():
    r = client.get("/app/owner")
    assert r.status_code == 200
    assert "Coord Hub" in r.text
    assert "coordination-hub/snapshot" in r.text
