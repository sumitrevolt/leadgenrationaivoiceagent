"""Daily video producer — gates, backpressure, engine choice, idempotency.

Every test drives a synthetic client id. Real ids (e.g. `jiya-makeover`) must
never appear: `video_pipeline` writes `delivery_ledger` events, and that ledger
is a TRACKED file — a test render against a real id commits fabricated delivery
events for a paying customer.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from app.marketing import daily_video

_CID = "test-daily-video-client"


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Point the producer's state files at tmp so runs never touch real stores.

    Both are RESOLVERS, not constants — the runtime-data ratchet rejects a store
    frozen to `data/...` at import, so they go through runtime_data_authority.
    """
    monkeypatch.setattr(daily_video, "_STATE", lambda: str(tmp_path / "daily_video.json"))
    monkeypatch.setattr(daily_video, "_STATE_TMP", lambda: str(tmp_path / "daily_video.json.tmp"))
    monkeypatch.setattr(
        daily_video, "_BLOCKS", lambda: str(tmp_path / "daily_video_advanced_block.json")
    )
    monkeypatch.setattr(
        daily_video, "_BLOCKS_TMP", lambda: str(tmp_path / "daily_video_advanced_block.json.tmp")
    )
    for key in (
        "DAILY_VIDEO_ADVANCED_BLOCK_DAYS",
        "DAILY_VIDEO_ENABLED",
        "DAILY_VIDEO_CLIENTS",
        "DAILY_VIDEO_ENGINE",
        "DAILY_VIDEO_MAX_PENDING",
        "DAILY_VIDEO_MAX_PER_RUN",
        "DAILY_VIDEO_ADVANCED_FAIL_WINDOW",
        "CREATIVE_OS_ENABLED",
        "CREATIVE_PROVIDER_HYPERFRAMES_ENABLED",
        "CREATIVE_HYPERFRAMES_CANARY_TENANTS",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def _fake_clients(monkeypatch, clients):
    from app.marketing import video_ad_cycle

    monkeypatch.setattr(video_ad_cycle, "_eligible_clients", lambda: list(clients))


# ------------------------------- master gate -------------------------------- #
def test_disabled_by_default_is_inert(monkeypatch):
    """No flag = no state write, no enqueue. Fail-closed default."""
    called = []
    monkeypatch.setattr(daily_video, "_enqueue_classic", lambda *a, **k: called.append(a) or {})
    out = asyncio.run(daily_video.run_daily())
    assert out["ran"] is False
    assert "DAILY_VIDEO_ENABLED" in out["reason"]
    assert called == []
    assert not os.path.exists(daily_video._STATE())


def test_empty_allowlist_refuses_every_client(monkeypatch):
    """Unset allowlist must mean NO tenant — not a fleet-wide daily render storm."""
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    _fake_clients(monkeypatch, [{"id": _CID, "business_name": "T"}])
    called = []
    monkeypatch.setattr(daily_video, "_enqueue_classic", lambda *a, **k: called.append(a) or {})
    out = asyncio.run(daily_video.run_daily())
    assert out["ran"] is False
    assert "fail-closed" in out["reason"]
    assert called == []


def test_client_allowed_star_and_explicit(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "")
    assert daily_video.client_allowed(_CID) is False
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "other-client")
    assert daily_video.client_allowed(_CID) is False
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", f"other-client,{_CID}")
    assert daily_video.client_allowed(_CID) is True
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "*")
    assert daily_video.client_allowed(_CID) is True


# ------------------------------- happy path --------------------------------- #
def test_enqueues_classic_once_per_day(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", _CID)
    _fake_clients(monkeypatch, [{"id": _CID, "business_name": "T"}])
    monkeypatch.setattr(daily_video, "open_review_count", lambda cid: 0)
    calls: list[tuple] = []

    def _fake(cid, day):
        calls.append((cid, day))
        return {"ok": True, "engine": "classic", "job_id": "j1"}

    monkeypatch.setattr(daily_video, "_enqueue_classic", _fake)

    first = asyncio.run(daily_video.run_daily())
    assert first["enqueued"] == 1
    assert len(calls) == 1

    # Second run the SAME day must be a no-op — a re-fired beat cannot double-bill
    # the customer's review inbox.
    second = asyncio.run(daily_video.run_daily())
    assert second["enqueued"] == 0
    assert len(calls) == 1
    assert any(s.get("reason") == "already_generated_today" for s in second["skipped"])

    with open(daily_video._STATE(), encoding="utf-8") as f:
        assert json.load(f)[_CID] == daily_video._today()


def test_failed_enqueue_does_not_burn_the_day(monkeypatch):
    """A dispatch failure must stay retryable on the next tick."""
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "*")
    _fake_clients(monkeypatch, [{"id": _CID, "business_name": "T"}])
    monkeypatch.setattr(daily_video, "open_review_count", lambda cid: 0)
    monkeypatch.setattr(
        daily_video, "_enqueue_classic", lambda cid, day: {"ok": False, "error": "broker down"}
    )
    out = asyncio.run(daily_video.run_daily())
    assert out["enqueued"] == 0
    assert daily_video._load_state().get(_CID) is None


# ------------------------------ backpressure -------------------------------- #
def test_pending_review_backlog_blocks_generation(monkeypatch):
    """Daily cadence must not grow the stuck-review pile (prod: 32/39 pending)."""
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "*")
    monkeypatch.setenv("DAILY_VIDEO_MAX_PENDING", "2")
    _fake_clients(monkeypatch, [{"id": _CID, "business_name": "T"}])
    monkeypatch.setattr(daily_video, "open_review_count", lambda cid: 2)
    called = []
    monkeypatch.setattr(daily_video, "_enqueue_classic", lambda *a: called.append(a) or {})
    out = asyncio.run(daily_video.run_daily())
    assert out["enqueued"] == 0
    assert called == []
    assert out["skipped"][0]["reason"] == "pending_review_backlog"
    assert out["skipped"][0]["open_reviews"] == 2


def test_per_run_cap_bounds_the_batch(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "*")
    monkeypatch.setenv("DAILY_VIDEO_MAX_PER_RUN", "2")
    _fake_clients(monkeypatch, [{"id": f"{_CID}-{i}", "business_name": "T"} for i in range(5)])
    monkeypatch.setattr(daily_video, "open_review_count", lambda cid: 0)
    monkeypatch.setattr(
        daily_video, "_enqueue_classic", lambda cid, day: {"ok": True, "job_id": "j"}
    )
    out = asyncio.run(daily_video.run_daily())
    assert out["enqueued"] == 2
    assert any("per_run_cap" in str(s.get("reason")) for s in out["skipped"])


# ------------------------------ engine choice ------------------------------- #
def test_advanced_gate_off_by_default(monkeypatch):
    ok, why = daily_video.advanced_gate(_CID)
    assert ok is False
    assert "CREATIVE_OS_ENABLED" in why


def test_advanced_gate_needs_provider_flag_and_tenant(monkeypatch):
    monkeypatch.setenv("CREATIVE_OS_ENABLED", "1")
    ok, why = daily_video.advanced_gate(_CID)
    assert ok is False and "HYPERFRAMES_ENABLED" in why

    monkeypatch.setenv("CREATIVE_PROVIDER_HYPERFRAMES_ENABLED", "1")
    ok, why = daily_video.advanced_gate(_CID)
    # Empty canary allowlist is fail-closed inside hyperframes_provider.
    assert ok is False and "CANARY_TENANTS" in why

    monkeypatch.setenv("CREATIVE_HYPERFRAMES_CANARY_TENANTS", _CID)
    ok, why = daily_video.advanced_gate(_CID)
    assert ok is True and why == "ok"


def test_auto_falls_back_to_classic_when_advanced_unavailable(monkeypatch):
    """This is the real prod condition: the HyperFrames toolchain image is not
    deployed, so `auto` must keep shipping a classic video instead of nothing."""
    engine, why = daily_video.choose_engine(_CID)
    assert engine == daily_video.ENGINE_CLASSIC
    assert "advanced unavailable" in why


def test_auto_downgrades_after_consecutive_advanced_failures(monkeypatch):
    monkeypatch.setenv("CREATIVE_OS_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_PROVIDER_HYPERFRAMES_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_HYPERFRAMES_CANARY_TENANTS", _CID)
    monkeypatch.setenv("DAILY_VIDEO_ADVANCED_FAIL_WINDOW", "2")

    monkeypatch.setattr(daily_video, "_recent_advanced_failures", lambda cid: 1)
    engine, _ = daily_video.choose_engine(_CID)
    assert engine == daily_video.ENGINE_ADVANCED

    monkeypatch.setattr(daily_video, "_recent_advanced_failures", lambda cid: 2)
    engine, why = daily_video.choose_engine(_CID)
    assert engine == daily_video.ENGINE_CLASSIC
    assert "auto downgrade" in why


def test_explicit_advanced_refuses_rather_than_silently_using_classic(monkeypatch):
    """`DAILY_VIDEO_ENGINE=advanced` is an operator assertion — honour it or
    report the refusal; never quietly ship a lower-tier deliverable."""
    monkeypatch.setenv("DAILY_VIDEO_ENGINE", "advanced")
    engine, why = daily_video.choose_engine(_CID)
    assert engine == ""
    assert "CREATIVE_OS_ENABLED" in why


def test_explicit_classic_never_touches_creative_os(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_ENGINE", "classic")
    monkeypatch.setenv("CREATIVE_OS_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_PROVIDER_HYPERFRAMES_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_HYPERFRAMES_CANARY_TENANTS", _CID)
    engine, why = daily_video.choose_engine(_CID)
    assert engine == daily_video.ENGINE_CLASSIC
    assert why == "DAILY_VIDEO_ENGINE=classic"


def test_advanced_engine_enqueues_via_creative_os(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "*")
    _fake_clients(monkeypatch, [{"id": _CID, "business_name": "T", "niche": "beauty"}])
    monkeypatch.setattr(daily_video, "open_review_count", lambda cid: 0)
    monkeypatch.setattr(
        daily_video, "choose_engine", lambda cid: (daily_video.ENGINE_ADVANCED, "forced")
    )
    seen: dict = {}

    def _fake_enqueue(**kwargs):
        seen.update(kwargs)
        return {"ok": True, "creative_id": "c1", "job_id": "j1"}

    import app.marketing.creative_os.service as svc

    monkeypatch.setattr(svc, "enqueue_generate", _fake_enqueue)
    out = asyncio.run(daily_video.run_daily())
    assert out["enqueued"] == 1
    assert seen["tenant_id"] == _CID
    assert seen["provider"] == "hyperframes"


# -------------------- permanent advanced refusal handling -------------------- #
def _force_advanced(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "*")
    monkeypatch.setenv("DAILY_VIDEO_ENGINE", "auto")
    # Advanced is genuinely reachable — the refusal comes from the BRIEF, not the
    # gate, which is the case that used to loop invisibly.
    monkeypatch.setenv("CREATIVE_OS_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_PROVIDER_HYPERFRAMES_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_HYPERFRAMES_CANARY_TENANTS", _CID)
    _fake_clients(monkeypatch, [{"id": _CID, "business_name": "T"}])
    monkeypatch.setattr(daily_video, "open_review_count", lambda cid: 0)
    monkeypatch.setattr(
        daily_video, "choose_engine", lambda cid: (daily_video.ENGINE_ADVANCED, "forced")
    )


def test_needs_customer_input_parks_tenant_and_still_ships_a_video(monkeypatch):
    """A brief refusal never fixes itself, and enqueue_generate records the
    attempt BEFORE dispatch — retrying daily would burn the tenant's Creative OS
    budget on records that never render, while the customer got nothing."""
    _force_advanced(monkeypatch)
    monkeypatch.setattr(
        daily_video,
        "_enqueue_advanced",
        lambda c: {
            "ok": False,
            "outcome": "needs_customer_input",
            "error": "brief_blocked",
            "missing": ["offer"],
        },
    )
    classic_calls: list[str] = []
    monkeypatch.setattr(
        daily_video,
        "_enqueue_classic",
        lambda cid, day: classic_calls.append(cid) or {"ok": True, "job_id": "j"},
    )

    out = asyncio.run(daily_video.run_daily())
    # Customer still gets today's video via classic.
    assert out["enqueued"] == 1
    assert classic_calls == [_CID]
    res = out["results"][0]
    assert res["fell_back_from"] == daily_video.ENGINE_ADVANCED
    assert "offer" in res["advanced_blocked"]

    # And the tenant is parked so tomorrow does not repeat the refused attempt.
    block = daily_video.advanced_block(_CID)
    assert block is not None
    ok, why = daily_video.advanced_gate(_CID)
    assert ok is False
    assert "advanced blocked" in why


def test_transient_advanced_failures_do_not_park_the_tenant(monkeypatch):
    """tenant_budget_exceeded / enqueue_failed DO clear on their own — parking
    on those would strand a healthy tenant on the lower-tier engine."""
    _force_advanced(monkeypatch)
    for transient in (
        {"ok": False, "error": "tenant_budget_exceeded"},
        {"ok": False, "error": "enqueue_failed:broker"},
    ):
        monkeypatch.setattr(daily_video, "_enqueue_advanced", lambda c, r=transient: dict(r))
        monkeypatch.setattr(daily_video, "_enqueue_classic", lambda cid, day: {"ok": False})
        asyncio.run(daily_video.run_daily())
        assert daily_video.advanced_block(_CID) is None


def test_explicit_advanced_does_not_silently_ship_classic_on_block(monkeypatch):
    """DAILY_VIDEO_ENGINE=advanced means advanced or nothing — record the block,
    do not quietly downgrade the deliverable."""
    _force_advanced(monkeypatch)
    monkeypatch.setenv("DAILY_VIDEO_ENGINE", "advanced")
    monkeypatch.setattr(
        daily_video,
        "_enqueue_advanced",
        lambda c: {"ok": False, "outcome": "blocked", "error": "brief_blocked"},
    )
    classic_calls: list[str] = []
    monkeypatch.setattr(
        daily_video, "_enqueue_classic", lambda cid, day: classic_calls.append(cid) or {"ok": True}
    )
    out = asyncio.run(daily_video.run_daily())
    assert classic_calls == []
    assert out["enqueued"] == 0
    assert daily_video.advanced_block(_CID) is not None


def test_block_expires_and_can_be_cleared(monkeypatch):
    daily_video._record_advanced_block(_CID, "needs_customer_input: offer")
    assert daily_video.advanced_block(_CID) is not None

    # Explicit operator clear (after the brief is completed).
    assert daily_video.clear_advanced_block(_CID)["cleared"] is True
    assert daily_video.advanced_block(_CID) is None

    # Auto-expiry: a stale block must not strand the tenant forever.
    daily_video._save_blocks({_CID: {"reason": "x", "at": "2020-01-01"}})
    assert daily_video.advanced_block(_CID) is None


# ---------------------- real open-review counting --------------------------- #
def test_open_review_count_collapses_latest_line_wins(monkeypatch, tmp_path):
    """The classic store is append-on-update JSONL — a record updated 5 times
    must count ONCE, and only in its LATEST state."""
    from app.marketing import video_ad_cycle

    store = tmp_path / "video_ads.jsonl"
    lines = [
        {"id": "a", "client_id": _CID, "status": "pending", "created_at": "2026-08-01T00:00:00"},
        {"id": "a", "client_id": _CID, "status": "approved", "created_at": "2026-08-01T00:00:00"},
        {"id": "b", "client_id": _CID, "status": "pending", "created_at": "2026-08-02T00:00:00"},
        {"id": "b", "client_id": _CID, "status": "pending", "created_at": "2026-08-02T00:00:00"},
        {"id": "c", "client_id": _CID, "status": "superseded", "created_at": "2026-08-03T00:00:00"},
        {
            "id": "d",
            "client_id": "someone-else",
            "status": "pending",
            "created_at": "2026-08-04T00:00:00",
        },
    ]
    store.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(video_ad_cycle, "_FILE", str(store))
    # Creative OS side contributes nothing here.
    monkeypatch.setattr(
        "app.marketing.creative_os.store.list_records", lambda *a, **k: {"items": []}
    )

    # 'a' latest = approved, 'b' latest = pending (once, not twice), 'c' superseded,
    # 'd' belongs to another tenant.
    assert daily_video.open_review_count(_CID) == 1


# --------------------------------- status ----------------------------------- #
def test_status_explains_why_nothing_runs(monkeypatch):
    _fake_clients(monkeypatch, [{"id": _CID, "business_name": "T"}])
    monkeypatch.setattr(daily_video, "open_review_count", lambda cid: 0)
    st = daily_video.status()
    assert st["ok"] is True
    assert st["enabled"] is False
    assert st["allowlist_configured"] is False
    row = next(r for r in st["clients"] if r["client_id"] == _CID)
    assert row["allowed"] is False
    assert row["advanced_gate_ok"] is False


def test_never_raises_when_eligible_clients_explodes(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "*")
    from app.marketing import video_ad_cycle

    def _boom():
        raise RuntimeError("store unreadable")

    monkeypatch.setattr(video_ad_cycle, "_eligible_clients", _boom)
    out = asyncio.run(daily_video.run_daily())
    assert out["ran"] is False
    assert "eligible_failed" in out["reason"]


# ------------------------------ wiring guards ------------------------------- #
def test_daily_video_is_a_registered_staff_job():
    from app.tasks.staff_jobs import STAFF_JOBS

    assert "daily_video" in STAFF_JOBS


def test_daily_video_has_a_dead_man_heartbeat_entry():
    from app.platform.automation_health import EXPECTED_GAP_MIN

    assert "daily_video" in EXPECTED_GAP_MIN


def test_daily_video_has_its_own_beat_entry_not_inside_content():
    """Regression guard for the actual prod defect: the video producer must NOT
    ride the `content` chain, where CONTENT_TIME_BUDGET_S silently skipped it."""
    from app.worker import celery_app

    entry = celery_app.conf.beat_schedule.get("staff-daily-video-daily")
    assert entry is not None
    assert entry["args"] == ("daily_video",)


def test_daily_video_task_routes_to_the_video_queue(monkeypatch):
    from app.worker import _route_video_task

    monkeypatch.setenv("CELERY_VIDEO_QUEUE", "1")
    assert _route_video_task("app.tasks.video_jobs.daily_video_client_task", (), {}, {}) == {
        "queue": "video"
    }
    monkeypatch.setenv("CELERY_VIDEO_QUEUE", "0")
    assert _route_video_task("app.tasks.video_jobs.daily_video_client_task", (), {}, {}) is None


def test_run_cycle_defers_generation_for_daily_owned_clients(monkeypatch, tmp_path):
    """The 5-day loop must not double-generate for a client the daily producer
    owns — that would put TWO videos and two approval asks in the same inbox."""
    from app.marketing import video_ad_cycle

    monkeypatch.setenv("VIDEO_AD_CYCLE", "1")
    monkeypatch.setenv("DAILY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", _CID)
    monkeypatch.setattr(video_ad_cycle, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(video_ad_cycle, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(
        video_ad_cycle,
        "_eligible_clients",
        lambda: [{"id": _CID}, {"id": "other-client"}],
    )
    generated: list[str] = []

    async def _fake_generate(cid, note="", revision=0, supersedes=""):
        generated.append(cid)
        return {"ok": True, "id": "x"}

    async def _noop_publish(limit=20):
        return {}

    async def _noop_regen(limit=10):
        return 0

    monkeypatch.setattr(video_ad_cycle, "generate_for_client", _fake_generate)
    monkeypatch.setattr(video_ad_cycle, "publish_due", _noop_publish)
    monkeypatch.setattr(video_ad_cycle, "_regen_due", _noop_regen)

    out = asyncio.run(video_ad_cycle.run_cycle())
    assert out["ran"] is True
    assert generated == ["other-client"]
    assert out["deferred_to_daily_video"] == 1


def test_run_cycle_still_generates_when_daily_producer_is_off(monkeypatch, tmp_path):
    """Existing every-N-day behaviour is unchanged while DAILY_VIDEO_ENABLED is off."""
    from app.marketing import video_ad_cycle

    monkeypatch.setenv("VIDEO_AD_CYCLE", "1")
    monkeypatch.delenv("DAILY_VIDEO_ENABLED", raising=False)
    monkeypatch.setenv("DAILY_VIDEO_CLIENTS", "*")
    monkeypatch.setattr(video_ad_cycle, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(video_ad_cycle, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(video_ad_cycle, "_eligible_clients", lambda: [{"id": _CID}])
    generated: list[str] = []

    async def _fake_generate(cid, note="", revision=0, supersedes=""):
        generated.append(cid)
        return {"ok": True, "id": "x"}

    monkeypatch.setattr(video_ad_cycle, "generate_for_client", _fake_generate)
    monkeypatch.setattr(video_ad_cycle, "publish_due", lambda limit=20: _async_none())
    monkeypatch.setattr(video_ad_cycle, "_regen_due", lambda limit=10: _async_zero())

    out = asyncio.run(video_ad_cycle.run_cycle())
    assert generated == [_CID]
    assert out["deferred_to_daily_video"] == 0


async def _async_none():
    return {}


async def _async_zero():
    return 0


def test_new_flags_are_in_the_automation_registry():
    from app.api.growth import AUTOMATION_FLAGS

    for flag in (
        "DAILY_VIDEO_ENABLED",
        "DAILY_VIDEO_CLIENTS",
        "DAILY_VIDEO_ENGINE",
        "CREATIVE_PROVIDER_HYPERFRAMES_ENABLED",
        "VIDEO_AD_INTERVAL_DAYS",
        "CELERY_VIDEO_QUEUE",
    ):
        assert flag in AUTOMATION_FLAGS, f"{flag} missing from AUTOMATION_FLAGS"
