"""office_hq — 8-room mapping, pipeline grouper, metrics/approvals composer.

Bars:
- Every STAFF key maps to a valid room (no orphan / no unknown room id).
- build_rooms_and_agents() never raises and rooms sum to all agents.
- build_pipeline() always returns exactly the 12 stages, each with a source tag.
- next_best_actions() is a pure function — no IO, deterministic on a fixed snapshot.
- build_snapshot() end-to-end never raises even with no DB/engines configured.
- pipeline_stage_detail() degrades gracefully for an unknown stage id.
"""

from __future__ import annotations

from app.platform import office_hq


def test_every_staff_member_maps_to_a_known_room():
    from app.platform.team import STAFF

    for key, meta in STAFF.items():
        room = office_hq.room_for_member(key, meta.get("product"))
        assert room in office_hq.ROOM_IDS, f"{key} mapped to unknown room {room}"


def test_room_defs_have_unique_ids():
    ids = [r["id"] for r in office_hq.ROOM_DEFS]
    assert len(ids) == len(set(ids)) == 8


def test_unmapped_member_falls_back_to_product_bucket():
    assert office_hq.room_for_member("__not_a_real_key__", "voice") == "voice_team"
    assert office_hq.room_for_member("__not_a_real_key__", "marketing") == "marketing_team"
    assert office_hq.room_for_member("__not_a_real_key__", "platform") == "platform_engineering"
    assert office_hq.room_for_member("__not_a_real_key__", None) == "platform_engineering"


def test_build_rooms_and_agents_never_raises_and_covers_full_roster():
    from app.platform.team import STAFF

    rooms, agents = office_hq.build_rooms_and_agents()
    assert len(rooms) == 8
    assert len(agents) == len(STAFF)
    total_in_rooms = sum(len(r["agent_keys"]) for r in rooms)
    assert total_in_rooms == len(STAFF)
    for r in rooms:
        assert r["status"] in ("idle", "active", "blocked", "error")


def test_runnable_members_are_a_subset_of_staff():
    from app.platform.team import STAFF

    assert office_hq.RUNNABLE_MEMBERS.issubset(set(STAFF.keys()))


async def test_build_pipeline_always_returns_12_tagged_stages():
    stages = await office_hq.build_pipeline()
    assert len(stages) == 12
    ids = [s["id"] for s in stages]
    assert len(ids) == len(set(ids))
    for s in stages:
        assert s["source"] in ("real", "partial", "mock")
        assert isinstance(s["count"], int)
        assert isinstance(s["items"], list)
        assert len(s["items"]) <= 3


async def test_build_snapshot_never_raises_and_has_all_sections():
    snap = await office_hq.build_snapshot()
    assert snap["ok"] is True
    for key in ("rooms", "agents", "metrics", "pipeline", "approvals", "system_health", "next_best_actions"):
        assert key in snap


async def test_pipeline_stage_detail_unknown_id_is_safe():
    out = await office_hq.pipeline_stage_detail("not_a_real_stage")
    assert out["source"] == "mock"
    assert out["items"] == []


def test_next_best_actions_is_pure_and_deterministic():
    snapshot = {
        "metrics": {"payments_pending": 2},
        "approvals": {"counts": {"pending": 3}},
        "system_health": {"overdue": ["a", "b"]},
        "pipeline": [
            {"id": "retention_growth", "errorCount": 1},
            {"id": "deal_conversion", "stuckCount": 4},
            {"id": "conversation_followup", "stuckCount": 0},
            {"id": "scoring_qualification", "count": 5},
        ],
    }
    actions = office_hq.next_best_actions(snapshot)
    assert len(actions) <= 6
    labels = " ".join(a["label"] for a in actions)
    assert "3 draft" in labels
    assert "2 automation" in labels
    assert "2 payment" in labels
    # Deterministic re-run (pure function, no IO/randomness).
    assert office_hq.next_best_actions(snapshot) == actions


def test_next_best_actions_empty_snapshot_is_safe():
    assert office_hq.next_best_actions({}) == []


def test_needs_approval_matches_pending_draft_title_substring():
    titles = ["sharma electricals — outreach draft", "plan: weekly seo batch"]
    assert office_hq._needs_approval("Sharma Electricals", titles) is True
    assert office_hq._needs_approval("Totally Unrelated Co", titles) is False
    assert office_hq._needs_approval("", titles) is False
    assert office_hq._needs_approval("ab", titles) is False  # too short, avoids noisy false-positives


def test_is_resolved_reads_stuck_resolved_at_from_overrides():
    overrides = {"L1": {"stuck_resolved_at": "2026-07-01T00:00:00+00:00"}, "L2": {}}
    assert office_hq._is_resolved(overrides, "L1") is True
    assert office_hq._is_resolved(overrides, "L2") is False
    assert office_hq._is_resolved(overrides, "L3") is False
    assert office_hq._is_resolved({}, "L1") is False


def test_apply_override_merges_owner_next_action_status_and_clears_sla():
    item = {"id": "L1", "type": "lead", "assignedAgentId": None, "nextAction": "Review karo",
            "status": "new", "slaRisk": True}
    overrides = {"L1": {"owner_agent": "rohan", "next_action": "Call at 5pm",
                         "status_override": "callback", "stuck_resolved_at": "2026-07-01T00:00:00+00:00"}}
    out = office_hq._apply_override(item, overrides)
    assert out["assignedAgentId"] == "rohan"
    assert out["nextAction"] == "Call at 5pm"
    assert out["status"] == "callback"
    assert out["slaRisk"] is False


def test_apply_override_is_noop_when_nothing_set():
    item = {"id": "L1", "type": "lead", "assignedAgentId": None, "slaRisk": True}
    assert office_hq._apply_override(dict(item), {}) == item
    assert office_hq._apply_override(dict(item), {"L1": {}}) == item


def test_move_item_rejects_unknown_stage_and_type(monkeypatch, tmp_path):
    from app.platform import admin_pipeline_overrides as apo

    monkeypatch.setattr(apo, "_STORE", str(tmp_path / "overrides.jsonl"))
    bad_deal = office_hq.move_item("d1", "deal", "not_a_real_stage")
    assert bad_deal["ok"] is False
    bad_type = office_hq.move_item("x1", "campaign", "won")
    assert bad_type["ok"] is False


def test_move_item_lead_writes_a_validated_status_override(monkeypatch, tmp_path):
    from app.platform import admin_pipeline_overrides as apo

    monkeypatch.setattr(apo, "_STORE", str(tmp_path / "overrides.jsonl"))
    ok = office_hq.move_item("L1", "lead", "callback", by="tester")
    assert ok["ok"] is True
    assert apo.get_override("L1")["status_override"] == "callback"
    bad = office_hq.move_item("L1", "lead", "not_a_status", by="tester")
    assert bad["ok"] is False


def test_pipeline_item_mutation_helpers_roundtrip(monkeypatch, tmp_path):
    from app.platform import admin_pipeline_overrides as apo

    monkeypatch.setattr(apo, "_STORE", str(tmp_path / "overrides.jsonl"))
    office_hq.assign_item_owner("L2", "swara", by="tester")
    office_hq.set_item_next_action("L2", "Call back tomorrow", by="tester")
    office_hq.resolve_item_stuck("L2", by="tester")
    ov = apo.get_override("L2")
    assert ov["owner_agent"] == "swara"
    assert ov["next_action"] == "Call back tomorrow"
    assert "stuck_resolved_at" in ov


def test_enum_value_unwraps_enum_member_not_str_repr():
    """Regression: str(SomeEnum.MEMBER) is 'ClassName.MEMBER' in Python, not the
    value — a real footgun for status/source comparisons. This locks the fix in."""
    from app.models.lead import LeadSource, LeadStatus

    class FakeLead:
        status = LeadStatus.APPOINTMENT
        source = LeadSource.GOOGLE_MAPS

    assert office_hq._enum_value(FakeLead(), "status") == "appointment"
    assert office_hq._enum_value(FakeLead(), "source") == "google_maps"

    class FakePlainString:
        status = "callback"

    assert office_hq._enum_value(FakePlainString(), "status") == "callback"

    class FakeNone:
        status = None

    assert office_hq._enum_value(FakeNone(), "status") == ""
