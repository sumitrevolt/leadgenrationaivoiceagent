"""Unit tests for the customer "Aapka Office" virtual-office aggregator
(app/api/customer_dashboard_builders.py). Direct builder calls — no app/auth/DB
so they stay fast and deterministic offline."""

from app.api.customer_dashboard_builders import (
    _build_office,
    _office_tasks,
    _rel_time,
)
from app.api.customer_dashboard_models import OnboardingChecklist, OnboardingStep


def _onboarding(done_ids: set[str]) -> OnboardingChecklist:
    ids = ["login", "profile", "setup", "minisite", "content", "leads"]
    steps = [OnboardingStep(id=i, label=i, done=(i in done_ids), hint="") for i in ids]
    done = sum(1 for s in steps if s.done)
    return OnboardingChecklist(
        steps=steps, done=done, total=len(steps),
        pct=round(done / len(steps) * 100, 1), complete=done >= len(steps),
    )


def test_rel_time_buckets():
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    assert _rel_time(now) == "abhi"
    assert "min pehle" in _rel_time(now - timedelta(minutes=10))
    assert "ghante" in _rel_time(now - timedelta(hours=3))
    assert _rel_time(now - timedelta(days=1)) == "kal"
    assert _rel_time(None) == ""


def test_every_task_has_impact_and_severity():
    """Core promise: har manual task me 'why' + automation-impact + severity ho."""
    ob = _onboarding(set())  # nothing done -> max tasks
    tasks = _office_tasks(
        {"plan": "trial"}, "combo", ob, approvals_pending=2,
        trial=None, routing_set=False, hot_leads=3,
    )
    assert tasks, "combo with empty onboarding should yield tasks"
    for t in tasks:
        assert t.get("title") and t.get("why") and t.get("impact"), t
        assert t.get("severity") in ("high", "medium", "low"), t
        assert t.get("cta_target"), t
    # sorted: first task severity must be 'high' when high tasks exist
    assert tasks[0]["severity"] == "high"


def test_product_aware_marketing_vs_voice():
    ob = _onboarding({"login", "profile", "setup"})  # mid setup
    mkt = _office_tasks({}, "marketing", ob, 2, None, False, 0)
    voice = _office_tasks({}, "voice", ob, 2, None, False, 4)
    mkt_ids = {t["id"] for t in mkt}
    voice_ids = {t["id"] for t in voice}
    # marketing-only tasks
    assert "approvals" in mkt_ids and "minisite" in mkt_ids
    assert "approvals" not in voice_ids and "minisite" not in voice_ids
    # voice-only tasks
    assert "routing" in voice_ids and "hotleads" in voice_ids
    assert "routing" not in mkt_ids and "hotleads" not in mkt_ids


def test_no_tasks_when_all_done():
    ob = _onboarding({"login", "profile", "setup", "minisite", "content", "leads"})
    tasks = _office_tasks({}, "marketing", ob, 0, None, True, 0)
    assert tasks == []


def test_build_office_never_raises_and_shape():
    o = _build_office("does-not-exist-client-xyz")
    assert isinstance(o, dict)
    for k in ("ok", "enabled", "product", "headline", "your_tasks", "activity", "summary"):
        assert k in o, k
    assert o["product"] in ("marketing", "voice", "combo")
    assert isinstance(o["your_tasks"], list)
    assert isinstance(o["activity"], list)
