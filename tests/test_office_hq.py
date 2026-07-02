"""office_hq — 8-room mapping, pipeline grouper, metrics/approvals composer,
offline_reason classification.

Bars:
- Every STAFF key maps to a valid room (no orphan / no unknown room id).
- build_rooms_and_agents() never raises and rooms sum to all agents.
- build_pipeline() always returns exactly the 12 stages, each with a source tag.
- next_best_actions() is a pure function — no IO, deterministic on a fixed snapshot.
- build_snapshot() end-to-end never raises even with no DB/engines configured.
- pipeline_stage_detail() degrades gracefully for an unknown stage id.
- classify_offline_reason() never raises and only surfaces for offline agents.
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


async def test_safe_collect_live_stats_degrades_on_timeout(monkeypatch):
    """Regression: _collect_live_stats() is SYNC and took 45s+ against real
    prod data (2026-07-01 incident) — confirmed via a live VPS timing probe.
    A slow/hanging call must degrade to {} within the timeout budget, never
    hang the whole snapshot again."""
    import time as _time

    def _slow():
        _time.sleep(2)
        return {"real_calls_today": 5}

    import app.api.admin_dashboard_builders as adb

    monkeypatch.setattr(adb, "_collect_live_stats", _slow)
    out = await office_hq._safe_collect_live_stats(timeout=0.2)
    assert out == {}


async def test_safe_collect_live_stats_returns_value_when_fast(monkeypatch):
    import app.api.admin_dashboard_builders as adb

    monkeypatch.setattr(adb, "_collect_live_stats", lambda: {"real_calls_today": 7})
    out = await office_hq._safe_collect_live_stats(timeout=5)
    assert out == {"real_calls_today": 7}


async def test_safe_db_call_times_out_and_returns_none():
    import asyncio

    async def _slow():
        await asyncio.sleep(2)
        return "never"

    out = await office_hq._safe_db_call(_slow(), timeout=0.2, label="test")
    assert out is None


async def test_build_metrics_accepts_prefetched_live_stats_without_refetching(monkeypatch):
    """Regression: build_metrics/build_pipeline used to each call
    _collect_live_stats() independently (2x cost). Passing a pre-fetched
    live_stats dict must be used as-is, with zero additional calls."""
    calls = {"n": 0}

    async def _tracking_safe_collect(*a, **kw):
        calls["n"] += 1
        return {}

    monkeypatch.setattr(office_hq, "_safe_collect_live_stats", _tracking_safe_collect)
    out = await office_hq.build_metrics(live_stats={"real_calls_today": 9, "estimated_mrr": 500})
    assert out["calls_completed_today"] == 9
    assert out["mrr"] == 500
    assert calls["n"] == 0  # never called _safe_collect_live_stats — used the pre-fetched dict


def test_snapshot_cache_ttl_exceeds_frontend_poll_interval():
    """Regression 2026-07-01: TTL was 15s while office_map.html polls every
    25s (setInterval(refreshSnapshot, 25000)) — every periodic auto-refresh
    was ALWAYS a cache miss since the cache had already expired by the time
    the next poll fired. TTL must stay strictly greater than the poll
    interval for the periodic refresh itself to ever be fast."""
    FRONTEND_POLL_INTERVAL_SEC = 25
    assert office_hq._SNAPSHOT_CACHE_TTL > FRONTEND_POLL_INTERVAL_SEC


class _FakeCache:
    """Minimal async in-memory stand-in for app.cache.CacheService, so caching
    logic is testable without a real Redis instance."""

    def __init__(self):
        self.store: dict[str, Any] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl=None):
        import json

        self.store[key] = json.loads(json.dumps(value))  # deep-copy like real JSON round-trip
        return True

    async def delete(self, key):
        self.store.pop(key, None)
        return 1


async def test_build_snapshot_second_call_is_cached(monkeypatch):
    """Regression: 8s felt slow on every refresh — a repeat call within the
    TTL window must return the SAME data without recomputing."""
    import app.cache as cache_mod

    fake = _FakeCache()
    monkeypatch.setattr(cache_mod, "cache", fake)

    calls = {"n": 0}
    orig_rooms = office_hq.build_rooms_and_agents

    def _counting_rooms():
        calls["n"] += 1
        return orig_rooms()

    monkeypatch.setattr(office_hq, "build_rooms_and_agents", _counting_rooms)

    first = await office_hq.build_snapshot()
    assert first["cached"] is False
    assert calls["n"] == 1

    second = await office_hq.build_snapshot()
    assert second["cached"] is True
    assert calls["n"] == 1  # NOT recomputed — served from cache


async def test_invalidate_snapshot_cache_forces_recompute(monkeypatch):
    import app.cache as cache_mod

    fake = _FakeCache()
    monkeypatch.setattr(cache_mod, "cache", fake)

    await office_hq.build_snapshot()
    assert fake.store  # something cached
    await office_hq.invalidate_snapshot_cache()
    assert not fake.store  # cleared

    second = await office_hq.build_snapshot()
    assert second["cached"] is False  # recomputed, not served stale


async def test_build_snapshot_works_when_cache_backend_is_broken(monkeypatch):
    """Cache is a pure perf optimization — a broken Redis must never break the page."""
    import app.cache as cache_mod

    class _BrokenCache:
        async def get(self, key):
            raise ConnectionError("redis down")

        async def set(self, key, value, ttl=None):
            raise ConnectionError("redis down")

        async def delete(self, key):
            raise ConnectionError("redis down")

    monkeypatch.setattr(cache_mod, "cache", _BrokenCache())
    snap = await office_hq.build_snapshot()
    assert snap["ok"] is True
    await office_hq.invalidate_snapshot_cache()  # must not raise either


async def test_build_snapshot_calls_collect_live_stats_only_once(monkeypatch):
    calls = {"n": 0}
    orig = office_hq._safe_collect_live_stats

    async def _counting(*a, **kw):
        calls["n"] += 1
        return await orig(*a, **kw)

    monkeypatch.setattr(office_hq, "_safe_collect_live_stats", _counting)
    await office_hq.build_snapshot()
    assert calls["n"] == 1


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


# --- offline_reason classification (added fdadb26, restored+merged after
# fdadb26 accidentally deleted all tests above this line) ---------------------


def test_offline_reason_flag_off(monkeypatch):
    monkeypatch.delenv("SOCIAL_ENGINE", raising=False)  # unset = off
    reason = office_hq.classify_offline_reason("zara")
    assert reason == "flag_off:SOCIAL_ENGINE"


def test_offline_reason_flag_on_no_data(monkeypatch):
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    reason = office_hq.classify_offline_reason("anika")
    assert reason == "no_data_today"


def test_offline_reason_unknown_member():
    reason = office_hq.classify_offline_reason("not_a_real_key")
    assert reason == "unknown"


def test_offline_reason_never_raises(monkeypatch):
    # Simulate a broken env read — must still return a string, never raise.
    import os
    original_environ = os.environ
    try:
        monkeypatch.setattr(office_hq.os, "environ", None)
        reason = office_hq.classify_offline_reason("zara")
        assert isinstance(reason, str)
    finally:
        monkeypatch.setattr(office_hq.os, "environ", original_environ)


def test_build_rooms_and_agents_includes_offline_reason_only_when_offline():
    rooms, agents = office_hq.build_rooms_and_agents()
    for a in agents:
        if a["status"] == "offline":
            assert a["offline_reason"] is not None
            assert isinstance(a["offline_reason"], str)
        else:
            assert a["offline_reason"] is None
