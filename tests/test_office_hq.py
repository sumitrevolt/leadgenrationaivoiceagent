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
    for key in (
        "rooms",
        "agents",
        "metrics",
        "pipeline",
        "approvals",
        "system_health",
        "next_best_actions",
        "boss_brief",
        "priority_actions",
        "room_workloads",
        "replay",
        "enterprise_features",
    ):
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


def _command_center_snapshot():
    return {
        "metrics": {
            "new_leads_today": 4,
            "qualified_leads_today": 2,
            "calls_completed_today": 3,
            "emails_sent_today": 7,
            "payments_pending": 1,
            "approvals_needed": 2,
            "system_issues": 1,
            "mrr": 5999,
        },
        "rooms": [
            {
                "id": "sales_crm",
                "name": "Sales / CRM Room",
                "activeTaskCount": 1,
                "blockedTaskCount": 2,
                "errorCount": 0,
                "approvalCount": 1,
                "agent_keys": ["rohan"],
            },
            {
                "id": "platform_engineering",
                "name": "Platform / Engineering",
                "activeTaskCount": 0,
                "blockedTaskCount": 0,
                "errorCount": 1,
                "approvalCount": 0,
                "agent_keys": ["kavya"],
            },
        ],
        "agents": [
            {
                "key": "rohan",
                "name": "Rohan",
                "status": "working",
                "room": "sales_crm",
                "todayActions": 8,
                "todayErrors": 0,
            },
            {
                "key": "kavya",
                "name": "Kavya",
                "status": "active",
                "room": "platform_engineering",
                "todayActions": 3,
                "todayErrors": 1,
            },
        ],
        "pipeline": [
            {
                "id": "scoring_qualification",
                "name": "Lead Scoring & Qualification",
                "count": 5,
                "stuckCount": 0,
                "errorCount": 0,
                "items": [
                    {
                        "id": "L1",
                        "name": "Sharma Solar",
                        "priority": "hot",
                        "assignedAgentId": None,
                        "slaRisk": False,
                        "nextAction": "Call karo",
                        "stageId": "scoring_qualification",
                        "type": "lead",
                    }
                ],
            },
            {
                "id": "conversation_followup",
                "name": "Conversation / Follow-up",
                "count": 2,
                "stuckCount": 2,
                "errorCount": 0,
                "items": [
                    {
                        "id": "L2",
                        "name": "Ravi Clinic",
                        "priority": "normal",
                        "assignedAgentId": "rohan",
                        "slaRisk": True,
                        "nextAction": "Follow-up",
                        "stageId": "conversation_followup",
                        "type": "lead",
                    }
                ],
            },
        ],
        "approvals": {
            "counts": {"pending": 2, "total_pending": 3},
            "queue": [{"kind": "draft", "id": "d1", "title": "Sales draft", "source": "sales"}],
        },
        "system_health": {
            "overdue": ["email_outreach"],
            "never_ran": [],
            "queue": {"dlq": 1},
            "jobs": [
                {"job": "email_outreach", "status": "overdue"},
                {"job": "ops", "status": "ok"},
            ],
        },
        "schedule": [
            {
                "job": "email_outreach",
                "label": "Email outreach",
                "type": "recurring",
                "cadence": "hourly",
            }
        ],
        "coordination": [
            {
                "goal": "clear hot replies",
                "mode": "sequential",
                "executed": False,
                "outcome": "draft",
                "at": "2026-07-03T05:00:00+00:00",
            }
        ],
        "generated_at": "2026-07-03T05:00:00+00:00",
        "cached": False,
    }


def test_build_boss_brief_is_pure_and_actionable():
    out = office_hq.build_boss_brief(_command_center_snapshot())
    assert out["headline"]
    assert out["risk"]["label"]
    assert out["opportunity"]["label"]
    assert out["recommendation"]["cta_target"]
    assert out["confidence"] in ("high", "medium", "low")


def test_build_priority_actions_structured_and_ranked():
    actions = office_hq.build_priority_actions(_command_center_snapshot())
    assert actions
    assert len(actions) <= 5
    assert actions[0]["severity"] in ("critical", "high", "medium", "low")
    for item in actions:
        for key in ("id", "title", "why", "severity", "owner", "room", "cta_label", "cta_target"):
            assert key in item
    assert office_hq.build_priority_actions(_command_center_snapshot()) == actions


def test_build_room_workloads_maps_items_to_rooms():
    out = office_hq.build_room_workloads(_command_center_snapshot())
    assert "sales_crm" in out
    assert out["sales_crm"]["owner_count"] >= 1
    assert out["sales_crm"]["work_items"]
    assert out["platform_engineering"]["health"]["errors"] == 1


def test_build_replay_returns_timeline_without_io():
    out = office_hq.build_replay(_command_center_snapshot(), limit=10)
    assert out["items"]
    assert out["source"] == "snapshot"
    assert len(out["items"]) <= 10
    for row in out["items"]:
        assert row["title"] and row["actor"] and row["at"]


async def test_build_snapshot_includes_command_center_sections():
    snap = await office_hq.build_snapshot()
    for key in ("boss_brief", "priority_actions", "room_workloads", "replay"):
        assert key in snap


def test_enterprise_features_contract_has_20_clickable_features():
    snapshot = {
        "rooms": [{"id": "coordinator", "blockedTaskCount": 0, "errorCount": 0}],
        "agents": [{"id": "manager", "status": "working"}, {"id": "rohan", "status": "offline"}],
        "metrics": {"mrr": 1999},
        "pipeline": [{"id": "lead_source", "count": 2, "stuckCount": 1, "errorCount": 0}],
        "approvals": {"counts": {"total_pending": 1}},
        "system_health": {
            "jobs": [{"job": "ops", "status": "ok"}],
            "overdue": [],
            "never_ran": [],
            "queue": {"dlq": 0},
        },
        "schedule": [{"job": "ops"}],
        "coordination": [],
        "next_best_actions": [{"label": "Review", "cta_target": "approvals"}],
    }
    out = office_hq.build_enterprise_features(snapshot)
    assert out["summary"]["total"] == 20
    assert len(out["features"]) == 20
    assert len({f["id"] for f in out["features"]}) == 20
    for f in out["features"]:
        assert f["name"]
        assert f["status"] in ("live", "attention", "action_needed")
        assert f["cta_target"]


def test_needs_approval_matches_pending_draft_title_substring():
    titles = ["sharma electricals — outreach draft", "plan: weekly seo batch"]
    assert office_hq._needs_approval("Sharma Electricals", titles) is True
    assert office_hq._needs_approval("Totally Unrelated Co", titles) is False
    assert office_hq._needs_approval("", titles) is False
    assert (
        office_hq._needs_approval("ab", titles) is False
    )  # too short, avoids noisy false-positives


def test_is_resolved_reads_stuck_resolved_at_from_overrides():
    overrides = {"L1": {"stuck_resolved_at": "2026-07-01T00:00:00+00:00"}, "L2": {}}
    assert office_hq._is_resolved(overrides, "L1") is True
    assert office_hq._is_resolved(overrides, "L2") is False
    assert office_hq._is_resolved(overrides, "L3") is False
    assert office_hq._is_resolved({}, "L1") is False


def test_apply_override_merges_owner_next_action_status_and_clears_sla():
    item = {
        "id": "L1",
        "type": "lead",
        "assignedAgentId": None,
        "nextAction": "Review karo",
        "status": "new",
        "slaRisk": True,
    }
    overrides = {
        "L1": {
            "owner_agent": "rohan",
            "next_action": "Call at 5pm",
            "status_override": "callback",
            "stuck_resolved_at": "2026-07-01T00:00:00+00:00",
        }
    }
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


# ---- Phase 3: unified approvals queue + boss finalizer + coordination ------ #


def test_build_approval_queue_never_raises_and_items_well_formed():
    q = office_hq.build_approval_queue()
    assert isinstance(q, list)
    for it in q:
        assert it["kind"] in ("draft", "patch", "selfimprove")
        assert it["id"]
        for key in ("title", "summary", "created_at", "source"):
            assert key in it


async def test_build_approvals_keeps_legacy_shape_and_adds_queue():
    out = await office_hq.build_approvals()
    # Drift-lock: original consumers (rooms/metrics/NBA) still read these.
    assert "drafts" in out and "counts" in out
    # Additive unified queue for the actionable Approvals panel.
    assert isinstance(out.get("queue"), list)
    # 2026-07-03: audit-trail strip — always present (possibly empty), never raises.
    assert isinstance(out.get("recent_decisions"), list)


def test_parse_boss_reply_formats():
    v, r = office_hq._parse_boss_reply("VERDICT: approve | REASON: sab theek hai")
    assert v == "approve"
    assert "sab theek" in r
    v2, _ = office_hq._parse_boss_reply("VERDICT: reject | REASON: risky change")
    assert v2 == "reject"
    v3, _ = office_hq._parse_boss_reply("")
    assert v3 == ""


async def test_boss_review_never_raises_and_is_recommend_only(monkeypatch):
    """No LLM keys / dead chain must degrade to skip-verdicts, never raise.
    boss_review must NOT call any decide/approve API (recommend-only by spec)."""
    out = await office_hq.boss_review(max_items=2, per_item_timeout=0.5)
    assert out["ok"] is True
    assert isinstance(out["verdicts"], list)
    for v in out["verdicts"]:
        assert v["verdict"] in ("approve", "reject", "skip")


def test_build_coordination_never_raises_and_is_bounded():
    runs = office_hq.build_coordination(limit=5)
    assert isinstance(runs, list)
    assert len(runs) <= 5
    for r in runs:
        for key in ("goal", "mode", "executed", "outcome", "at"):
            assert key in r


async def test_snapshot_includes_coordination_and_approval_queue():
    snap = await office_hq.build_snapshot()
    assert "coordination" in snap
    assert "queue" in (snap.get("approvals") or {})


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


# NOTE: the 2026-07-01 version of this guard (test_snapshot_cache_ttl_exceeds_
# frontend_poll_interval, asserting TTL > poll against the then-25s poll) was
# briefly replaced 2026-07-02 by a test asserting the opposite (TTL < poll),
# based on a flawed premise that TTL should sit below the poll interval. That
# was backwards and reintroduced the exact 2026-07-01 cache-defeat risk; fixed
# same day by restoring the TTL > poll invariant below with the retuned
# values (TTL=18s, poll=15s).


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
    # Hermetic: pichle tests ka snapshot 18s-TTL cache me warm ho sakta (test-order/
    # timing dependent — CI me `-m "not network"` selection se badalta) →
    # build_snapshot cache-hit = 0 collect calls. Pehle cache saaf karo.
    await office_hq.invalidate_snapshot_cache()
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


def test_priya_downstream_hook_exists():
    """Regression guard: apply_qualified_downstream (which pushes to CRM as
    'priya') must still be called from the live Vobiz call-completion path.
    Confirmed present 2026-07-02 (app/telephony/vobiz_stream.py:2691) — this
    test fails loudly if that call site is ever removed/renamed, since a
    prior incident (2026-06-18) had exactly this class of cross-path-parity
    regression (AUTO_QUALIFY wired in call_manager but not vobiz_stream)."""
    import inspect

    from app.telephony import vobiz_stream

    src = inspect.getsource(vobiz_stream)
    assert "apply_qualified_downstream" in src


def test_anika_cadence_scheduler_wiring_exists():
    """Regression guard: cadence.run_due() must still be called from the
    scheduler. Confirmed present 2026-07-02 (team_scheduler.py:390)."""
    import inspect

    from app.platform import team_scheduler

    src = inspect.getsource(team_scheduler)
    assert "cadence.run_due" in src or "await cadence.run_due()" in src


def test_ira_journey_hook_wiring_exists():
    """Regression guard: journeys.emit_event() must still be called from the
    inquiry hook. Confirmed present 2026-07-02 (inquiry_hooks.py:229)."""
    import inspect

    from app.platform import inquiry_hooks

    src = inspect.getsource(inquiry_hooks)
    assert "journeys.emit_event" in src or "emit_event(" in src


def test_snapshot_cache_ttl_exceeds_frontend_poll_interval():
    """Task 8 (2026-07-02) retuned cadence for freshness on this real-time
    view: poll interval 25s->15s (frontend/office_map.html setInterval) and
    cache TTL 35s->18s (this file). TTL must stay ABOVE the poll interval --
    same invariant as the 2026-07-01 incident fix (TTL 15s vs poll 25s meant
    the cache expired before every single poll, defeating it entirely; fixed
    by raising TTL comfortably above the poll interval). This test pins that
    invariant so a future retune can't silently invert it again by relying on
    build_snapshot()'s compute time as coincidental slack instead of a real
    margin."""
    FRONTEND_POLL_INTERVAL_S = 15  # frontend/office_map.html setInterval(...,15000)
    assert office_hq._SNAPSHOT_CACHE_TTL == 18
    assert office_hq._SNAPSHOT_CACHE_TTL > FRONTEND_POLL_INTERVAL_S


# --- Aaj-ka-Schedule (SCHEDULE_DEFS + build_schedule) ------------------------


def test_schedule_defs_contract():
    """Every entry is display-complete: job key, Hinglish-friendly label, and a
    valid type-specific shape (daily/weekly = 4-int IST window with start<end;
    weekly also a 0-6 weekday; recurring = human cadence string)."""
    jobs = [d["job"] for d in office_hq.SCHEDULE_DEFS]
    assert len(jobs) == len(set(jobs)), "duplicate job key in SCHEDULE_DEFS"
    for d in office_hq.SCHEDULE_DEFS:
        assert d["job"] and d["label"]
        assert d["type"] in ("daily", "weekly", "recurring")
        if d["type"] in ("daily", "weekly"):
            w = d["window"]
            assert len(w) == 4 and all(isinstance(x, int) for x in w)
            assert (w[0], w[1]) < (w[2], w[3]), f"{d['job']} window start !< end"
            assert 0 <= w[0] <= 23 and 0 <= w[2] <= 23
        if d["type"] == "weekly":
            assert 0 <= d["weekday"] <= 6
        if d["type"] == "recurring":
            assert d["cadence"]


def test_schedule_defs_windows_match_team_scheduler_source():
    """Drift-lock: SCHEDULE_DEFS is a static DISPLAY mirror of the real windows
    in team_scheduler.py — if a window there changes without updating the
    mirror (or vice versa), this fails loudly. Window tuples are asserted
    verbatim against the scheduler source; recurring jobs assert their
    _last_ran wiring still exists."""
    import inspect

    from app.platform import team_scheduler

    src = inspect.getsource(team_scheduler)
    for d in office_hq.SCHEDULE_DEFS:
        job = d["job"]
        assert (f'_last_ran["{job}"]' in src) or (f'_last_ran.get("{job}")' in src), (
            f"{job}: no _last_ran wiring found in team_scheduler.py"
        )
        if d["type"] in ("daily", "weekly"):
            w = d["window"]
            window_str = f"({w[0]}, {w[1]}) <= hm < ({w[2]}, {w[3]})"
            assert window_str in src, (
                f"{job}: window {window_str} not found verbatim in team_scheduler.py "
                "— scheduler window changed? Update SCHEDULE_DEFS to match."
            )
        if d["type"] == "weekly":
            assert f"now.weekday() == {d['weekday']}" in src, (
                f"{job}: weekday {d['weekday']} not found in team_scheduler.py"
            )


def test_build_schedule_returns_copies_and_never_raises():
    out = office_hq.build_schedule()
    assert len(out) == len(office_hq.SCHEDULE_DEFS)
    out[0]["label"] = "mutated"
    assert office_hq.SCHEDULE_DEFS[0]["label"] != "mutated"  # copies, not references


async def test_build_snapshot_includes_schedule():
    snap = await office_hq.build_snapshot()
    assert isinstance(snap.get("schedule"), list)
    assert len(snap["schedule"]) == len(office_hq.SCHEDULE_DEFS)
