"""Owner OS v1 — inventory, command bus, kills, approvals, auth."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import get_current_user, require_admin
from app.main import app
from app.platform import owner_os
from app.platform import owner_os_store as store
from app.platform.office_hq import RUNNABLE_MEMBERS
from app.platform.team import STAFF

client = TestClient(app)


def _patch_stores(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OWNER_OS_STORAGE", "jsonl")
    store.reset_storage_mode()
    monkeypatch.setattr(owner_os, "_CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(owner_os, "_KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(owner_os, "_AUDIT_STORE", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(store, "CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(store, "KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(store, "AUDIT_STORE", str(tmp_path / "audit.jsonl"))


def test_owner_os_requires_admin():
    saved_admin = app.dependency_overrides.pop(require_admin, None)
    saved_user = app.dependency_overrides.pop(get_current_user, None)
    try:
        r = client.get("/api/admin/owner-os/home")
        assert r.status_code in (401, 403)
    finally:
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user


def test_owner_os_page_served():
    r = client.get("/app/owner")
    assert r.status_code == 200
    assert "Owner OS" in r.text
    assert (
        "Pause Manual Runs" in r.text
        or "Calling OFF" in r.text
        or "Calling HARD OFF" in r.text
        or "Calling LIVE" in r.text
    )


def test_canonical_agent_count_consistency(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    r = client.get("/api/admin/owner-os/agents")
    assert r.status_code == 200
    body = r.json()
    assert body.get("staff_count") == 31
    assert len(body.get("agents") or []) == 31
    inv = body.get("inventory") or {}
    assert inv.get("canonical_agents") == 31
    assert inv.get("system_supervisors") == 1
    assert inv.get("service_identities") == 4
    assert inv.get("orphan_runnable_ids") == []
    assert "manager" in STAFF
    assert STAFF["manager"]["name"] == "Boss"
    assert any(a.get("id") == "manager" and a.get("name") == "Boss" for a in body["agents"])
    assert any(s.get("id") == "manager" for s in body.get("system_supervisors") or [])
    dumped = json.dumps(body)
    assert "sk-" not in dumped.lower()
    assert "Bearer" not in dumped
    maturity = body.get("maturity") or {}
    assert maturity.get("enterprise_profiles_ready") == 31
    assert maturity.get("ok") is True
    assert sum((maturity.get("rollout_counts") or {}).values()) == 31


def test_owner_os_maturity_projection_is_admin_read_only(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    r = client.get("/api/admin/owner-os/maturity")
    assert r.status_code == 200
    body = r.json()
    assert body["staff_count"] == body["enterprise_profiles_ready"] == 31
    assert len(body["agents"]) == 31
    assert body["claim_note"].startswith("Profile-ready is not rollout-live")
    assert all(row["memory"]["private_by_default"] for row in body["agents"])
    assert all(row["skills"]["role_specific"] for row in body["agents"])


def test_no_orphan_runnable_ids():
    orphans = sorted(k for k in RUNNABLE_MEMBERS if k not in STAFF)
    assert orphans == []
    assert "manager" in RUNNABLE_MEMBERS
    assert "manager" in STAFF


def test_parse_and_run_jiya_status_report(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    text = (
        "Jiya ke pending deliverables ka status report banao. "
        "Koi content publish ya customer message mat bhejna."
    )
    plan = owner_os.parse_intent(text)
    assert plan["intent"] == "status_report"
    assert plan["tenant_id"] == "jiya-makeover"
    assert plan["safe_to_execute"] is True
    assert plan["publish_allowed"] is False
    assert plan["customer_notify_allowed"] is False
    assert plan["risk_level"] == "low"
    assert any("publish" in x.lower() for x in plan["will_not_perform"])

    out = owner_os.run_now(text, actor="test@admin", idempotency_key="jiya-report-1")
    executed = (out.get("executed") or {}).get("command") or {}
    assert executed.get("status") == "SUCCEEDED"
    assert executed.get("publish_allowed") is False
    assert executed.get("customer_notify_allowed") is False
    ev = executed.get("evidence") or {}
    assert ev.get("tenant_id") == "jiya-makeover"
    assert ev.get("publish") is False
    assert ev.get("customer_notify") is False
    # audit created
    audit = owner_os.recent_audit(20)
    assert any(a.get("action") == "command_execute" for a in audit)


def test_enable_calling_refused(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    plan = owner_os.parse_intent("Swara calling enable karo platform_dial on")
    assert plan["intent"] == "enable_calling"
    assert plan["approval_required"] is True
    assert plan["safe_to_execute"] is False
    r = client.post(
        "/api/admin/owner-os/kill-switches",
        json={"key": "platform_dial", "engaged": False, "reason": "test"},
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "phrase",
    ["Enable calling", "enable calls", "start calling", "Call chalu karo"],
)
def test_enable_calling_phrase_synonyms_refused(phrase, monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    plan = owner_os.parse_intent(phrase)
    assert plan["intent"] == "enable_calling", phrase
    assert plan["risk_level"] == "critical", phrase
    assert plan["safe_to_execute"] is False, phrase


def test_idempotent_command_create(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    a = owner_os.create_command("Pending approvals dikhao", actor="t", idempotency_key="idem-1")
    b = owner_os.create_command("Pending approvals dikhao", actor="t", idempotency_key="idem-1")
    assert a["command"]["command_id"] == b["command"]["command_id"]
    assert b.get("deduped") is True


def test_command_state_transitions(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    assert owner_os.can_transition("READY", "QUEUED")
    assert not owner_os.can_transition("SUCCEEDED", "CANCELLED")
    assert not owner_os.can_transition("SUCCEEDED", "RUNNING")
    created = owner_os.create_command(
        "Pending approvals dikhao", actor="t", idempotency_key="st-1", confirm=False
    )
    cid = created["command"]["command_id"]
    # succeed then cancel must fail
    owner_os._update_command(cid, status="QUEUED")
    owner_os.execute_command(cid, actor="t")
    cur = owner_os.get_command(cid)
    assert cur["status"] == "SUCCEEDED"
    bad = owner_os.cancel_command(cid, actor="t")
    assert bad.get("ok") is False


def test_duplicate_execute_prevented(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    text = "Sab agents ki current duty batao"
    out = owner_os.run_now(text, actor="t", idempotency_key="dup-exec-1")
    cid = ((out.get("executed") or {}).get("command") or {}).get("command_id")
    assert cid
    again = owner_os.execute_command(cid, actor="t")
    assert again.get("deduped") is True or (again.get("command") or {}).get("status") == "SUCCEEDED"


def test_concurrent_command_create(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    key = "concurrent-idem-1"
    results = []

    def _one():
        return owner_os.create_command("Pending approvals dikhao", actor="t", idempotency_key=key)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_one) for _ in range(8)]
        for f in as_completed(futs):
            results.append(f.result())
    ids = {r["command"]["command_id"] for r in results}
    assert len(ids) == 1


def test_owner_kill_blocks_all_agents(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_all_agents", True, by="test", reason="unit")
    block = owner_os.owner_kill_blocks("status_report")
    assert block and "owner_all_agents" in block


def test_kill_publishing_via_social_pause(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_publishing", True, by="test", reason="unit")
    assert owner_os.kill_engaged("owner_publishing") is True
    from app.social_engine.pause import should_pause_job

    paused, reason = should_pause_job({"platform": "instagram", "client_id": "jiya-makeover"})
    assert paused is True
    assert reason == "owner_publishing_kill"


def test_kill_bulk_email_entry(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_bulk_email", True, by="test", reason="unit")
    assert owner_os.kill_engaged("owner_bulk_email") is True


def test_kill_whatsapp_auto_send(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    owner_os.set_kill_switch("owner_whatsapp_outbound", True, by="test", reason="unit")
    from app.marketing.whatsapp_campaign import auto_send_enabled

    assert auto_send_enabled() is False


def test_manual_pause_wording(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    reg = owner_os.agent_registry()
    sem = reg.get("pause_semantics") or {}
    assert sem.get("label_pause") == "Pause Manual Runs"
    assert "Scheduled jobs may continue" in (sem.get("note") or "")
    plan = owner_os.parse_intent("Isha ko pause karo")
    assert plan["intent"] == "pause_agent"
    assert any("Scheduled" in x or "scheduler" in x.lower() for x in plan["will_not_perform"])


def test_scheduler_not_blocked_by_manual_pause(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    ok, reason = owner_os.scheduler_dispatch_allowed("isha")
    assert ok is True
    owner_os.set_kill_switch("owner_schedulers", True, by="t", reason="unit")
    ok2, reason2 = owner_os.scheduler_dispatch_allowed("isha")
    assert ok2 is False
    assert reason2 == "owner_schedulers_kill_switch"


def test_unknown_intent_fail_closed(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    plan = owner_os.parse_intent("drop database and ssh into prod")
    assert plan["intent"] == "unknown"
    assert plan["safe_to_execute"] is False
    assert plan["status"] == "APPROVAL_REQUIRED"


def test_approval_decide_bridge(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    calls = []

    def _fake_decide(source, item_id, decision, by="admin", reason=""):
        calls.append((source, item_id, decision, by, reason))
        if len(calls) > 1:
            return {"ok": True, "source": source, "id": item_id, "status": "approved", "noop": True}
        return {"ok": True, "source": source, "id": item_id, "status": "approved", "action": "ok"}

    monkeypatch.setattr("app.platform.approvals_bridge.decide", _fake_decide)
    a = owner_os.decide_approval("sales", "item-1", "approve", actor="admin@test")
    b = owner_os.decide_approval("sales", "item-1", "approve", actor="admin@test")
    assert a.get("ok") is True
    assert b.get("noop") is True
    content = owner_os.decide_approval("content", "c1", "approve", actor="admin@test")
    assert content.get("ok") is False
    blob = "%s %s" % (content.get("open_in") or "", content.get("reason") or "")
    assert "Mission Control" in blob


def test_cross_tenant_status_report_scoped(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    out = owner_os.run_now(
        "Jiya ke pending deliverables ka status report banao. Publish mat karna.",
        actor="t",
        idempotency_key="tenant-scope-1",
    )
    ev = ((out.get("executed") or {}).get("command") or {}).get("evidence") or {}
    assert ev.get("tenant_id") == "jiya-makeover"
    # evidence must not claim another tenant
    assert "other-client" not in json.dumps(ev)


def test_secret_free_home(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    home = owner_os.owner_home()
    dumped = json.dumps(home)
    assert "sk-" not in dumped.lower()
    assert "password" not in dumped.lower()
    assert home.get("calling_badge") in (
        "Calling OFF",
        "Calling OFF (voice kill)",
        "Calling LIVE (compliance on)",
    ) or str(home.get("calling_badge") or "").startswith("Calling LIVE")
    assert home.get("inventory", {}).get("canonical_agents") == 31
    assert "speed_to_lead_badge" in home


def test_calling_posture_live_when_dial_enabled(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setattr("app.platform.platform_dial.enabled", lambda: True)
    monkeypatch.setattr("app.platform.platform_dial.dial_limit", lambda: 10)

    class _Kill:
        engaged = False

    monkeypatch.setattr("app.telephony.voice_launch.admin_kill_status", lambda: _Kill())
    p = owner_os.calling_posture()
    assert p["live"] is True
    assert "LIVE" in p["badge"]
    home = owner_os.owner_home()
    assert home.get("calling_live") is True


def test_calling_posture_off_when_dial_disabled(monkeypatch, tmp_path):
    _patch_stores(monkeypatch, tmp_path)
    monkeypatch.setattr("app.platform.platform_dial.enabled", lambda: False)

    class _Kill:
        engaged = False

    monkeypatch.setattr("app.telephony.voice_launch.admin_kill_status", lambda: _Kill())
    p = owner_os.calling_posture()
    assert p["live"] is False
    assert p["badge"] == "Calling OFF"
