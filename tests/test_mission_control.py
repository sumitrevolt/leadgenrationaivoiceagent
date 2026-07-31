"""Mission control chat ingress + burn-in gate tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.platform import mission_control as mc


def test_parse_launch_ready():
    p = mc.parse_chat_command("launch-ready")
    assert p["ok"] is True
    assert p["template"] == "launch_ready"
    assert p["safety_lane"] == "GREEN"


def test_parse_pause_amber():
    p = mc.parse_chat_command("pause cursor_impl")
    assert p["ok"] is True
    assert p["verb"] == "pause"
    assert p["arg"] == "cursor_impl"
    assert p["safety_lane"] == "AMBER"


def test_create_mission_records_executor_truth(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    def _off_proof(**kwargs):
        return {"status": "flag_off", "session_id": None, "available": False}

    monkeypatch.setattr(
        "app.integrations.openclaw.owner_os_adapter.prove_edge_receipt",
        _off_proof,
        raising=False,
    )
    monkeypatch.setattr(
        "app.integrations.openclaw.policies.openclaw_enabled",
        lambda: False,
        raising=False,
    )
    out = mc.create_mission(
        "revenue_ready", actor="test@local", base_sha="abc123", idempotency_key="k-rev"
    )
    assert out["ok"] is True
    m = out["mission"]
    assert m["base_sha"] == "abc123"
    assert "PLATFORM_DIAL_DAILY" in m["red_gates_held"]
    ex = out["executors"]
    assert ex["cursor"]["session_id"] is None
    assert ex["cursor"]["status"] != "available"
    assert ex["opencode_verifier"]["status"] == "unavailable"
    assert ex["opencode_verifier"]["session_id"] is None
    assert all(p["state"] == "MANUAL_OR_UNAVAILABLE" for p in m["packets"])
    assert (tmp_path / "data/mission_control/ledger.jsonl").is_file()


def test_openclaw_probe_can_become_available(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    def _proof(**kwargs):
        return {
            "status": "available",
            "session_id": "oc_deadbeefcafebabe",
            "available": True,
            "command": "platform.status",
            "command_id": "ocmd_cafebabe",
            "correlation_id": "oc_deadbeefcafebabe",
            "verified": True,
            "note": "test receipt",
        }

    monkeypatch.setattr(
        "app.integrations.openclaw.policies.openclaw_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.integrations.openclaw.owner_os_adapter.prove_edge_receipt",
        _proof,
    )
    ex = mc.probe_executors()
    assert ex["openclaw"]["status"] == "available"
    assert ex["openclaw"]["session_id"] == "oc_deadbeefcafebabe"
    assert ex["cursor"]["session_id"] is None
    out = mc.create_mission("income_today", actor="t", base_sha="sha", idempotency_key="k-income")
    oc = [p for p in out["mission"]["packets"] if p["agent"] == "openclaw"][0]
    assert oc["state"] == "READY"
    assert oc["executor_session_id"] == "oc_deadbeefcafebabe"


def test_idempotent_mission_create(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    a = mc.create_mission("launch_ready", actor="t", idempotency_key="k1")
    b = mc.create_mission("launch_ready", actor="t", idempotency_key="k1")
    assert a["mission"]["mission_id"] == b["mission"]["mission_id"]
    assert b.get("deduped") is True


def test_create_requires_idempotency_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    out = mc.create_mission("launch_ready", actor="t")
    assert out["ok"] is False
    assert out["error"] == "idempotency_key_required"


def test_chat_amber_always_parks_even_with_confirm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    created = mc.create_mission("income_today", actor="t", idempotency_key="k-roll")
    mid = created["mission"]["mission_id"]
    out = mc.handle_chat(f"rollback {mid}", actor="t", confirm=True)
    assert out["status"] == "APPROVAL_REQUIRED"
    assert mc._read_mission(mid)["state"] == "CREATED"


def test_typed_amber_rollback_with_confirm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    created = mc.create_mission("income_today", actor="t", idempotency_key="k-roll2")
    mid = created["mission"]["mission_id"]
    out = mc.apply_amber_action("rollback", mid, actor="t", confirm=True)
    assert out["status"] == "ROLLED_BACK"
    assert mc._read_mission(mid)["state"] == "ROLLED_BACK"


def test_amber_requires_confirm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    out = mc.apply_amber_action("pause", "cursor_impl", actor="t", confirm=False)
    assert out["status"] == "APPROVAL_REQUIRED"


def test_chat_unknown():
    out = mc.handle_chat("enable everything", actor="t")
    assert out["ok"] is False


def test_mission_handlers_registered():
    from app.integrations.openclaw.mission_commands import MISSION_GREEN, MISSION_HANDLERS
    from app.integrations.openclaw.policies import AMBER_COMMANDS, GREEN_COMMANDS

    assert "mission.launch_ready" in GREEN_COMMANDS
    assert "mission.rollback" in AMBER_COMMANDS
    assert set(MISSION_HANDLERS) >= MISSION_GREEN


def test_openclaw_spawn_requires_idempotency_key():
    from app.integrations.openclaw.mission_commands import _spawn

    out = _spawn("launch_ready", {}, actor="t", correlation_id="corr-unique-1")
    assert out["status"] == "FAILED"
    assert out["result"]["error"] == "idempotency_key_required"


def test_idempotent_after_many_missions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    # Create many other keys, then prove stable key still dedupes via index (not scan-cap).
    for i in range(220):
        mc.create_mission("launch_ready", actor="t", idempotency_key=f"bulk-{i}")
    a = mc.create_mission("launch_ready", actor="t", idempotency_key="stable-key")
    b = mc.create_mission("launch_ready", actor="t", idempotency_key="stable-key")
    assert a["mission"]["mission_id"] == b["mission"]["mission_id"]
    assert b.get("deduped") is True


def test_burn_in_blocker_zero_is_pass():
    path = Path(__file__).resolve().parents[1] / "scripts" / "prod_burn_in.py"
    spec = importlib.util.spec_from_file_location("prod_burn_in", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sample = {
        "health_code": 200,
        "status": "healthy",
        "environment": "production",
        "version": "abc",
        "ready_code": 200,
        "ready_status": "healthy",
        "db": "healthy",
        "redis": "healthy",
        "activation_code": 200,
        "ready_for_launch": True,
        "blocker_count": 0,
        "payments_ready": True,
        "http_/pricing": 200,
        "http_/start": 200,
        "http_/api/billing/plans": 200,
        "http_/api/public/pay-info": 200,
    }
    assert mod._ok_sample(sample, "abc") == []
