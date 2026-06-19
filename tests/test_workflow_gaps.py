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


def test_journey_ensure_active_when_engine_on(monkeypatch):
    from app.marketing import journeys

    monkeypatch.setenv("JOURNEY_ENGINE", "1")
    # fresh store
    import os

    for p in ("data/journeys.jsonl", "data/journey_runs.jsonl"):
        if os.path.exists(p):
            os.remove(p)
    n = journeys.ensure_active_defaults()
    assert n == 1
    assert any(r.get("enabled") for r in journeys.list_journeys())
