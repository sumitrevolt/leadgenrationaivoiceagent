"""Tests — AI-automation infra batch (llm_metrics, automation_health, flags API).
Sync + tmp stores. No network/Redis needed (DLQ routes defensive — yahan sirf
pure parts test hote).
"""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _load_automation_health_audit():
    path = Path(__file__).resolve().parent.parent / "scripts" / "automation_health_audit.py"
    spec = importlib.util.spec_from_file_location("automation_health_audit_testmod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


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
    beats["growth"]["at"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(
        timespec="seconds"
    )
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


def test_automation_health_covers_durable_engineer_jobs():
    from app.platform import automation_health as ah

    for job in ("engineer_dbre", "engineer_dataquality", "engineer_deps"):
        assert job in ah.EXPECTED_GAP_MIN


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


def test_automation_health_audit_uses_last_tick_at(tmp_path, monkeypatch):
    aha = _load_automation_health_audit()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "self_improve_state.json").write_text(
        '{"last_tick_at":"2026-06-22T12:00:00+00:00","last_tick":1719057600}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(aha, "_now", lambda: datetime(2026, 6, 22, 12, 5, tzinfo=timezone.utc))
    out = aha.check_alive()
    assert out["status"] == "green"
    assert out["last_tick_min"] == 5


def test_automation_health_audit_dev_mode_without_loops_is_not_red(tmp_path, monkeypatch):
    aha = _load_automation_health_audit()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SELF_IMPROVE_LOOP", raising=False)
    monkeypatch.delenv("TEAM_AUTOMATION", raising=False)
    out = aha.check_alive()
    assert out["status"] == "green"
    assert "enabled" in out["detail"].lower()


def test_automation_health_audit_compliance_skips_inactive_outbound(tmp_path, monkeypatch):
    aha = _load_automation_health_audit()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AUTO_EMAIL_OUTREACH", raising=False)
    monkeypatch.delenv("SMS_DLT_ENABLED", raising=False)
    monkeypatch.delenv("DLT_APPROVED", raising=False)
    monkeypatch.setenv("VOBIZ_AUTH_ID", "test-id")
    monkeypatch.delenv("RECORDING_RETENTION", raising=False)
    out = aha.check_compliance()
    assert out["dlt_enabled"] is True
    assert out["optout_enforced"] is True
    assert out["retention_active"] is False
    assert out["status"] == "yellow"


def test_automation_health_audit_dlq_uses_queue_depth(monkeypatch):
    aha = _load_automation_health_audit()

    class FakeAutomationHealth:
        @staticmethod
        def queue_depth():
            return {"celery": 2, "heavy": 1, "dlq": 3, "dead": 0}

    monkeypatch.setattr(aha, "automation_health", FakeAutomationHealth)
    out = aha.check_dlq_status()
    assert out["status"] == "yellow"
    assert out["depths"]["dlq"] == 3
