"""STAFF bus — 31-agent manifest, envelope security, synthetic canaries."""

from __future__ import annotations

import os

import pytest

from app.platform.staff_bus import (
    EVENT_TYPES,
    StaffBus,
    build_envelope,
    build_manifest,
    run_all_staff_canaries,
    validate_envelope,
    validate_manifest,
)
from app.platform.staff_bus.canary import refuse_unknown_and_replay
from app.platform.staff_bus.runtime import reset_runtime_state_for_tests


@pytest.fixture()
def bus_root(tmp_path, monkeypatch):
    monkeypatch.setenv("STAFF_BUS_DATA_ROOT", str(tmp_path / "staff_bus"))
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "1")
    monkeypatch.setenv("BOSS_GOV_AUTHORITY_KEY", "test-staff-bus-authority")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("LEADGEN_RUNTIME_DATA_DIR", str(tmp_path / "runtime"))
    reset_runtime_state_for_tests()
    yield tmp_path
    reset_runtime_state_for_tests()


def test_manifest_exactly_31_no_comb():
    m = build_manifest()
    v = validate_manifest(m)
    assert v["ok"] is True, v
    assert v["workforce_count"] == 31
    assert v["team_count"] == 7
    assert v["boss"] == "manager"
    assert v["comb_in_staff"] is False
    ids = {a["agent_id"] for a in m["agents"]}
    assert "comb" not in ids
    assert "manager" in ids
    assert len(ids) == 31


def test_seven_teams_cover_all_workers():
    m = build_manifest()
    workers = {a["agent_id"] for a in m["agents"] if a["agent_id"] != "manager"}
    covered = {mem for t in m["teams"] for mem in (t.get("members") or [])}
    assert workers == covered
    assert len(m["teams"]) == 7


def test_envelope_unknown_and_malformed_fail_closed():
    bad = build_envelope(
        event_type="not.real",
        tenant_id="t1",
        source_agent_id="manager",
        destination="boss:manager",
        payload={"a": 1},
    )
    assert validate_envelope(bad)["fail_closed"] is True
    good = build_envelope(
        event_type="work.status",
        tenant_id="t1",
        source_agent_id="manager",
        destination="owner_os",
        payload={"ok": True},
    )
    assert validate_envelope(good)["ok"] is True
    assert "work.status" in EVENT_TYPES


def test_publish_idempotency_and_unknown_agent(bus_root):
    reset_runtime_state_for_tests()
    out = refuse_unknown_and_replay(StaffBus(require_flag=False))
    assert out["ok"] is True, out


def test_flag_off_is_inert(bus_root, monkeypatch):
    monkeypatch.delenv("STAFF_BUS_ENABLED", raising=False)
    bus = StaffBus(require_flag=True)
    out = bus.publish(
        event_type="work.status",
        tenant_id="t1",
        source_agent_id="manager",
        destination="owner_os",
        payload={"ping": 1},
    )
    assert out.get("inert") is True


def test_run_all_31_staff_canaries(bus_root):
    result = run_all_staff_canaries(data_root=str(bus_root / "cny"))
    assert result["total"] == 31
    assert result["go_count"] == 31, [
        (
            r["agent_id"],
            r.get("gate"),
            r.get("error"),
            r.get("decision_error"),
            r.get("advice_error"),
            r.get("boss_approve_error"),
            r.get("boss_review_error"),
        )
        for r in result["rows"]
        if r.get("gate") != "GO"
    ]
    assert result["ok"] is True
    assert result["protected_side_effects"] == 0
    assert result["comb_in_staff"] is False
    # Every row has correlation + terminal evidence
    for row in result["rows"]:
        assert row.get("source_event_id")
        assert row.get("terminal_event_id")
        assert row.get("audit_event_id")
        if row.get("decision_contract") == "no_decision_expected":
            assert row.get("decision_id") is None
        else:
            assert row.get("decision_id")
            assert row.get("advice_id")
            assert row.get("boss_verdict_id")


def test_staff_bus_flag_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS
    from app.platform.automation_flag_manifest import describe_flag

    assert "STAFF_BUS_ENABLED" in AUTOMATION_FLAGS
    meta = describe_flag("STAFF_BUS_ENABLED")
    assert meta is not None
    assert str(getattr(meta, "default", "0") or "0") in ("0", "false", "False")
