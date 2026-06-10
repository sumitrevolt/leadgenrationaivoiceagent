"""Tests — AI-automation infra batch (llm_metrics, automation_health, flags API).
Sync + tmp stores. No network/Redis needed (DLQ routes defensive — yahan sirf
pure parts test hote).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone


def test_llm_metrics_record_and_stats(tmp_path, monkeypatch):
    from app.platform import llm_metrics as lm

    monkeypatch.setattr(lm, "_LOG", str(tmp_path / "llm.jsonl"))
    lm.record("cerebras", True, 412.5)
    lm.record("cerebras", True, 380.0)
    lm.record("cerebras", False, 8000.0, "429 rate limit")
    lm.record("groq", True, 510.0)
    st = lm.stats()
    assert st["total_calls"] == 4
    cer = st["providers"]["cerebras"]
    assert cer["calls"] == 3 and 0 < cer["ok_rate"] < 1
    assert cer["last_error"].startswith("429")
    assert cer["avg_ms"] > 300
    assert st["fallback_or_fail_rate"] == 0.25
    # kabhi raise nahi — bad inputs
    lm.record("", True, -1)
    assert lm.stats()["total_calls"] == 5


def test_automation_health_heartbeat_and_overdue(tmp_path, monkeypatch):
    from app.platform import automation_health as ah

    monkeypatch.setattr(ah, "_RUNS", str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(ah, "_BEATS", str(tmp_path / "beats.json"))
    monkeypatch.delenv("AUTOMATION_HEALTH_ALERTS", raising=False)

    # fresh = sab never_ran
    h0 = ah.health()
    assert h0["status"] == "warming_up" and "growth" in h0["never_ran"]

    # growth abhi chala -> ok
    ah.record_run("growth", True, 2.5)
    h1 = ah.health()
    g = next(j for j in h1["jobs"] if j["job"] == "growth")
    assert g["status"] == "ok" and g["last_ok"] is True

    # growth ko 3 ghante purana kar do -> overdue (gap 60 min)
    import json

    beats = json.load(open(ah._BEATS, encoding="utf-8"))
    beats["growth"]["at"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")
    json.dump(beats, open(ah._BEATS, "w", encoding="utf-8"))
    h2 = ah.health()
    assert "growth" in h2["overdue"] and h2["status"] == "degraded"

    # watch gated-off pe bhi health lautata, kabhi raise nahi
    out = asyncio.run(ah.run_watch())
    assert out.get("overdue") == ["growth"]


def test_automation_health_failed_run(tmp_path, monkeypatch):
    from app.platform import automation_health as ah

    monkeypatch.setattr(ah, "_RUNS", str(tmp_path / "r.jsonl"))
    monkeypatch.setattr(ah, "_BEATS", str(tmp_path / "b.json"))
    ah.record_run("content", False, 1.0, "boom")
    h = ah.health()
    c = next(j for j in h["jobs"] if j["job"] == "content")
    assert c["status"] == "last_failed"


def test_flags_registry_route():
    from app.api.growth import AUTOMATION_FLAGS, router

    assert "DUNNING_ENGINE" in AUTOMATION_FLAGS and "GROWTH_OPTIMIZER" in AUTOMATION_FLAGS
    paths = {r.path for r in router.routes}
    for p in (
        "/growth/infra/llm",
        "/growth/infra/automation-health",
        "/growth/infra/dlq",
        "/growth/infra/dlq/retry",
        "/growth/infra/flags",
    ):
        assert p in paths, f"route missing: {p}"


def test_scheduler_heartbeat_wrapper():
    """_run_job wrapper exists + _run_job_inner dispatcher intact (import-level)."""
    from app.platform import team_scheduler as ts

    assert hasattr(ts, "_run_job") and hasattr(ts, "_run_job_inner")
    # unknown job -> inner kuch nahi karta, wrapper heartbeat record karta, no raise
    asyncio.run(ts._run_job("nonexistent_job_xyz"))
