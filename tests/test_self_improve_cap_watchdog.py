"""2026-07-28 — self-improve watchdog must not churn after daily_cap.

Prod evidence: 14 memcg OOM on leadgen_worker while SELF_IMPROVE_LOOP=1;
172 tick receives / 35 tick_slot / 17 daily_cap. After cap the owner chain
sleeps ~3600s; ensure_alive's 15-minute stale window treated that as death
and seeded parallel chains → tick_slot noise + worker RSS pressure.
"""

from __future__ import annotations

import json
import time

import app.agents.self_improve as si


def _patch_state(tmp_path, monkeypatch, **state):
    monkeypatch.setenv("SELF_IMPROVE_LOOP", "1")
    monkeypatch.setattr(si, "_STATE", str(tmp_path / "state.json"))
    with open(si._STATE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def test_ensure_alive_does_not_revive_same_day_daily_cap(tmp_path, monkeypatch):
    day = si._now().strftime("%Y-%m-%d")
    _patch_state(
        tmp_path,
        monkeypatch,
        day=day,
        status="daily_cap",
        last_tick=time.time() - 3600,  # would be "stale" under the old rule
        runs_today=60,
    )
    queued: list[bool] = []
    from app.tasks import staff_jobs

    monkeypatch.setattr(staff_jobs.self_improve_tick, "delay", lambda: queued.append(True))
    monkeypatch.setattr(si, "_acquire_revive_lock", lambda: True)
    monkeypatch.setattr(si, "_redis_client", lambda: None)

    out = si.ensure_alive()

    assert out.get("paused") == "daily_cap"
    assert out.get("alive") is True
    assert queued == [], "daily_cap same-day must not seed a parallel chain"


def test_ensure_alive_does_not_revive_while_next_tick_scheduled(tmp_path, monkeypatch):
    _patch_state(
        tmp_path,
        monkeypatch,
        day=si._now().strftime("%Y-%m-%d"),
        status="ok",
        last_tick=time.time() - 3600,
    )

    class FakeRedis:
        def get(self, key):
            if key == si._TICK_NEXT_ALLOWED_KEY:
                return str(time.time() + 3000)
            return None

        def set(self, *a, **k):
            return True

    monkeypatch.setattr(si, "_redis_client", lambda: FakeRedis())
    queued: list[bool] = []
    from app.tasks import staff_jobs

    monkeypatch.setattr(staff_jobs.self_improve_tick, "delay", lambda: queued.append(True))

    out = si.ensure_alive()

    assert out.get("scheduled") is True
    assert out.get("alive") is True
    assert queued == []


def test_ensure_alive_still_revives_true_death(tmp_path, monkeypatch):
    _patch_state(
        tmp_path,
        monkeypatch,
        day=si._now().strftime("%Y-%m-%d"),
        status="ok",
        last_tick=time.time() - 3600,
    )

    class FakeRedis:
        def get(self, key):
            return None

        def set(self, *a, **k):
            return True

    monkeypatch.setattr(si, "_redis_client", lambda: FakeRedis())
    monkeypatch.setattr(si, "_acquire_revive_lock", lambda: True)
    queued: list[bool] = []
    from app.tasks import staff_jobs

    monkeypatch.setattr(staff_jobs.self_improve_tick, "delay", lambda: queued.append(True))

    out = si.ensure_alive()

    assert out.get("revived") is True
    assert queued == [True]
