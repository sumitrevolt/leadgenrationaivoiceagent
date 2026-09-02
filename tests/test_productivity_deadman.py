"""A producer that runs but stops producing must be visible.

The liveness dead-man only knows a job RAN and did not raise — `record_run`
stores `{job, ok, s, duration_ms, note, at, trigger, started_at}` and nothing
about whether the run did any work. That stayed true for every one of the 15
days `video_ad_cycle` was gated inert (2026-07-22 -> 2026-08-06) while the
`content` job it rides heartbeat green. What actually exposed it was that
`video_ads.jsonl` stopped growing.

So this watches the OUTPUT store, which needs no change to any of the 44 staff
jobs.
"""

from __future__ import annotations

import os
import time

import pytest

from app.platform import automation_health, today_overview


@pytest.fixture
def _registry(tmp_path, monkeypatch):
    """Point the freshness registry at a single controllable store."""
    store = tmp_path / "producer.jsonl"

    def _install(**overrides):
        spec = {
            "resolver": lambda: str(store),
            "max_stale_days": 8,
            "why": "test producer",
            "owner_hint": "test hint",
        }
        spec.update(overrides)
        monkeypatch.setattr(automation_health, "OUTPUT_FRESHNESS", {"test_producer": spec})
        return store

    return _install


def _age(path, days: float):
    path.write_text("{}\n", encoding="utf-8")
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_fresh_output_is_not_reported(_registry):
    store = _registry()
    _age(store, 0.5)
    assert automation_health.stale_outputs() == []


def test_output_inside_budget_is_not_reported(_registry):
    store = _registry(max_stale_days=8)
    _age(store, 7.9)
    assert automation_health.stale_outputs() == []


def test_output_past_budget_is_reported_with_age_and_hint(_registry):
    store = _registry(max_stale_days=8)
    _age(store, 15.0)  # the real outage length
    out = automation_health.stale_outputs()
    assert len(out) == 1
    assert out[0]["status"] == "stale"
    assert out[0]["age_days"] >= 15
    assert out[0]["owner_hint"] == "test hint"


def test_missing_store_is_unknown_not_a_false_alarm(_registry, tmp_path):
    """A fresh deployment legitimately has no file yet — that must not page."""
    _registry(resolver=lambda: str(tmp_path / "never_written.jsonl"))
    out = automation_health.stale_outputs()
    assert len(out) == 1
    assert out[0]["status"] == "unknown"
    assert out[0]["age_days"] is None


def test_a_broken_resolver_never_raises(_registry):
    def _boom():
        raise RuntimeError("resolver exploded")

    _registry(resolver=_boom)
    assert automation_health.stale_outputs() == []


def test_health_degrades_on_stale_but_not_on_unknown(_registry, tmp_path, monkeypatch):
    store = _registry(max_stale_days=2)
    _age(store, 30.0)
    h = automation_health.health()
    assert h["outputs_stale"] is True
    assert h["ok"] is False
    assert h["status"] == "degraded"

    # "unknown" alone must leave health untouched.
    _registry(resolver=lambda: str(tmp_path / "absent.jsonl"))
    h2 = automation_health.health()
    assert h2["outputs_stale"] is False


def test_aaj_tab_names_the_producer_and_the_gap(monkeypatch):
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {
            "status": "degraded",
            "ok": False,
            "overdue": [],
            "never_ran": [],
            "queue": {},
            "jobs": [],
            "engine_skips": {"total": 0, "by_engine": {}, "by_job": {}},
            "engines_skipped_recently": False,
            "stale_outputs": [
                {
                    "producer": "video_ad_cycle",
                    "store": "/x/video_ads.jsonl",
                    "age_days": 15.0,
                    "status": "stale",
                    "max_stale_days": 8,
                    "why": "per-client AI video ads",
                    "owner_hint": "Video engine chup ho gaya",
                }
            ],
            "outputs_stale": True,
        },
    )
    out = today_overview.build()
    hits = [p for p in out["problems"] if "video_ad_cycle" in str(p.get("kya"))]
    assert hits, "a stalled producer must appear on the owner's Aaj tab"
    assert "15" in hits[0]["kya"]
    assert hits[0]["fix"] == "Video engine chup ho gaya"


def test_unknown_status_does_not_reach_the_aaj_tab(monkeypatch):
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {
            "status": "healthy",
            "ok": True,
            "overdue": [],
            "never_ran": [],
            "queue": {},
            "jobs": [],
            "engine_skips": {"total": 0, "by_engine": {}, "by_job": {}},
            "engines_skipped_recently": False,
            "stale_outputs": [{"producer": "p", "status": "unknown", "age_days": None}],
            "outputs_stale": False,
        },
    )
    out = today_overview.build()
    assert not [p for p in out["problems"] if "chal to raha hai" in str(p.get("kya"))]


# --------------------------- registry integrity ----------------------------- #
def test_the_real_registry_resolves_every_producer():
    """Each entry must point at a resolvable path — a typo'd resolver would
    silently degrade to 'unknown' and protect nothing."""
    for name, spec in automation_health.OUTPUT_FRESHNESS.items():
        assert callable(spec["resolver"]), name
        path = spec["resolver"]()
        assert isinstance(path, str) and path, name
        assert int(spec["max_stale_days"]) > 0, name
        assert spec["why"], name


def test_video_producer_is_registered():
    """This is the producer whose silent death started all of this."""
    assert "video_ad_cycle" in automation_health.OUTPUT_FRESHNESS
