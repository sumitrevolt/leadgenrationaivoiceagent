"""Tests — Hermes 🛰️ Infrastructure Handler agent (infra_handler.py)."""

from __future__ import annotations

import asyncio


def test_hermes_in_staff_roster_platform():
    from app.platform import team

    assert "hermes" in team.STAFF
    assert team.STAFF["hermes"]["product"] == "platform"
    # shared platform staff => dono products ke roster me dikhe
    assert "hermes" in team.staff_for_product("marketing")
    assert "hermes" in team.staff_for_product("voice")


def test_snapshot_defensive_and_scored(tmp_path, monkeypatch):
    from app.platform import infra_handler as ih

    monkeypatch.setattr(ih, "_STORE", tmp_path / "scans.jsonl")
    snap = asyncio.run(ih.snapshot())
    assert snap["agent"] == "hermes"
    assert isinstance(snap["score"], int) and 0 <= snap["score"] <= 100
    assert snap["status"] in ("healthy", "attention", "critical")
    assert set(snap["checks"]) == {"ready", "disk", "memory", "jobs", "llm", "backups", "embedder"}
    assert snap["actions"]  # hamesha kam-se-kam ek line


def test_run_watch_gated_off(monkeypatch):
    from app.platform import infra_handler as ih

    monkeypatch.delenv("INFRA_HANDLER", raising=False)
    out = asyncio.run(ih.run_watch())
    assert out["ok"] is True and "skipped" in out


def test_run_watch_on_records_scan(tmp_path, monkeypatch):
    from app.platform import infra_handler as ih

    monkeypatch.setenv("INFRA_HANDLER", "1")
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)  # email path inert
    monkeypatch.setattr(ih, "_STORE", tmp_path / "scans.jsonl")
    out = asyncio.run(ih.run_watch())
    assert out["ok"] is True and isinstance(out.get("score"), int)
    scans = ih.recent_scans()
    assert len(scans) == 1 and scans[0]["score"] == out["score"]


def test_flag_registered():
    from app.api.growth import AUTOMATION_FLAGS

    assert "INFRA_HANDLER" in AUTOMATION_FLAGS
