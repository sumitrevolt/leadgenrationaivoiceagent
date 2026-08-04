"""Owner OS litmus — ADR-155 deterministic HITL harvest."""

from __future__ import annotations

from pathlib import Path

from app.platform import owner_os
from app.platform import owner_os_litmus as litmus
from app.platform import owner_os_store as store


def _patch_stores(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OWNER_OS_STORAGE", "jsonl")
    store.reset_storage_mode()
    monkeypatch.setattr(owner_os, "_CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(owner_os, "_KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(owner_os, "_AUDIT_STORE", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(store, "CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(store, "KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(store, "AUDIT_STORE", str(tmp_path / "audit.jsonl"))


def test_plan_litmus_passes_status_report(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("OWNER_OS_LITMUS", "1")
    plan = owner_os.parse_intent(
        "Jiya ke pending deliverables ka status report banao. "
        "Koi content publish ya customer message mat bhejna."
    )
    assert plan["intent"] == "status_report"
    assert "litmus" in plan
    assert plan["litmus"]["ok"] is True
    assert plan["litmus"]["schema"] == "owner-os-litmus/1"
    assert "Litmus: PASS" in plan["preview_summary"]


def test_high_risk_litmus_requires_approval(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    plan = owner_os.parse_intent("bulk email saare clients ko bhejo")
    assert plan["approval_required"] is True
    assert plan["litmus"]["ok"] is True
    ids = {c["id"] for c in plan["litmus"]["checks"]}
    assert "high_risk_requires_approval" in ids


def test_execute_blocked_without_idempotency_when_litmus_on(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("OWNER_OS_LITMUS", "1")
    gated = litmus.gate_execute(
        {"status": "READY", "idempotency_key": ""},
        {"intent": "list_agents", "risk_level": "low", "approval_required": False},
    )
    assert gated["ok"] is False
    assert "idempotency_key_present" in (gated["litmus"]["failed_must"] or [])


def test_execute_bypasses_block_when_litmus_off(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("OWNER_OS_LITMUS", "0")
    gated = litmus.gate_execute(
        {"status": "READY", "idempotency_key": ""},
        {"intent": "list_agents", "risk_level": "low", "approval_required": False},
    )
    assert gated["ok"] is True
    assert gated.get("bypassed") is True


def test_owner_os_flag_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS
    from app.platform.automation_flag_manifest import describe_flag

    assert "OWNER_OS_LITMUS" in AUTOMATION_FLAGS
    meta = describe_flag("OWNER_OS_LITMUS")
    assert meta.default_hint == "1"
