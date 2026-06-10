"""Tests — infra batch-2 (telephony readiness, queue guard, new agents, ops page)."""

from __future__ import annotations

import asyncio


def test_telephony_readiness_checks(monkeypatch):
    from app.telephony import telephony_readiness as tr

    res = tr.run_checks()
    assert 0 <= res["score"] <= 100
    assert "exotel_creds" in res["checks"] and "tts_edge" in res["checks"]
    assert isinstance(res["actions"], list) and res["actions"]
    # creds unset env me -> missing me dikhe (defensive: config fallback ho sakta)
    assert isinstance(res["missing"], list)


def test_telephony_readiness_watch_never_raises(tmp_path, monkeypatch):
    from app.telephony import telephony_readiness as tr

    monkeypatch.setattr(tr, "_LOG", str(tmp_path / "tel.jsonl"))
    monkeypatch.delenv("TELEPHONY_READY_ALERTS", raising=False)
    out = asyncio.run(tr.run_watch())
    assert "score" in out
    out2 = asyncio.run(tr.run_watch())  # second run = prev_score compare path
    assert "score" in out2


def test_queue_depth_defensive_and_health_shape(tmp_path, monkeypatch):
    from app.platform import automation_health as ah

    monkeypatch.setattr(ah, "_RUNS", str(tmp_path / "r.jsonl"))
    monkeypatch.setattr(ah, "_BEATS", str(tmp_path / "b.json"))
    q = ah.queue_depth()  # Redis na ho -> -1, kabhi raise nahi
    assert set(q.keys()) == {"celery", "dlq"}
    h = ah.health()
    assert "queue" in h and "queue_backlogged" in h


def test_new_staff_in_roster():
    from app.platform.team import STAFF

    assert "tara" in STAFF and STAFF["tara"]["title"] == "Voice Infra Ops"
    assert "nikhil" in STAFF and "Revenue" in STAFF["nikhil"]["title"]
    assert len(STAFF) == 10  # 8 purane + 2 naye


def test_ops_routes_registered():
    from app.api.growth import router

    paths = {r.path for r in router.routes}
    assert "/growth/infra/telephony-readiness" in paths
    # /app/ops page route main.py me hai — yahan growth API hi check
