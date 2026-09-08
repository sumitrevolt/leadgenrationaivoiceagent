"""Workflow connection gaps — cadence enroll + journey defaults."""

from __future__ import annotations

import pytest


def test_cadence_enroll_rejects_source_kwarg():
    from app.marketing import cadence

    with pytest.raises(TypeError):
        cadence.enroll(lead={"phone": "9111111111"}, source="inquiry")


def test_cadence_enroll_accepts_source_in_lead_dict():
    from app.marketing import cadence

    r = cadence.enroll({"phone": "9222222222", "name": "t", "source": "inquiry"})
    assert r.get("id")


def test_journey_ensure_adds_inquiry_when_only_custom_rules(monkeypatch):
    from app.marketing import journeys

    monkeypatch.setenv("JOURNEY_ENGINE", "1")
    import os

    for p in ("data/journeys.jsonl", "data/journey_runs.jsonl"):
        if os.path.exists(p):
            os.remove(p)
    journeys.add_journey(
        "Custom manual", "manual", [{"type": "notify", "params": {}}], enabled=False
    )
    n = journeys.ensure_active_defaults()
    assert n == 1
    assert any(
        r.get("enabled") and r.get("trigger") == "inquiry_received"
        for r in journeys.list_journeys()
    )


def test_journey_ensure_still_adds_inquiry_when_other_trigger_enabled(monkeypatch, tmp_path):
    """Enabled signup/manual must NOT satisfy the inquiry default gate."""
    from app.marketing import journeys

    monkeypatch.setenv("JOURNEY_ENGINE", "1")
    monkeypatch.setattr(journeys, "_JOURNEYS", str(tmp_path / "journeys.jsonl"))
    monkeypatch.setattr(journeys, "_RUNS", str(tmp_path / "journey_runs.jsonl"))
    journeys.add_journey(
        "Signup only",
        "signup",
        [{"type": "draft_whatsapp", "params": {"topic": "welcome"}}],
        enabled=True,
    )
    n = journeys.ensure_active_defaults()
    assert n == 1
    rules = journeys.list_journeys()
    assert any(r.get("enabled") and r.get("trigger") == "signup" for r in rules)
    assert any(r.get("enabled") and r.get("trigger") == "inquiry_received" for r in rules)
