"""Locks that NEXT todos stay runnable: 3 WS, caps, owner surfaces, no 50/day live."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_next_todos_keeps_three_workstreams_and_money_order():
    text = (REPO / "docs" / "gtm" / "NEXT_TODOS.md").read_text(encoding="utf-8")
    assert "WS-GTM1" in text and "WS-BUZZ" in text and "WS-REV50" in text
    assert text.find("Hot Queue") < text.find("UPI Bind")
    assert "WEB_CONCURRENCY" in text and "CELERY_ONBOARD_QUEUE" in text
    assert "50/day live" in text or "50/day" in text
    assert "Do **not**" in text or "do not" in text.lower()


def test_hot_queue_blitz_is_owner_one_pager():
    text = (REPO / "docs" / "gtm" / "HOT_QUEUE_BLITZ_CHECKLIST.md").read_text(encoding="utf-8")
    assert "https://leadsgenai.in/app/inbox" in text
    assert "Admin token paste" in text or "token paste" in text.lower()
    assert "sec-upi-selfserve" in text
    assert "/app/admin-login" in text
    assert "human send" in text.lower() or "human send only" in text
    assert "Aaj naye paid" in text
    assert "max 10" in text.lower() or "Max 10" in text


def test_boss_canary_runbook_is_dry_run_first():
    canary = (REPO / "docs" / "gtm" / "BOSS_HARNESS_CANARY.md").read_text(encoding="utf-8")
    harness = (REPO / "scripts" / "buzz_start_harness.py").read_text(encoding="utf-8")
    assert "--dry-run" in canary and "--agent Boss" in canary
    assert "1b13cecc" in canary
    assert "sandbox" in canary.lower()
    assert "--dry-run" in harness


def test_web_concurrency_stays_two_and_onboard_queue_is_flag():
    compose = (REPO / "docker-compose.vps.yml").read_text(encoding="utf-8")
    assert "WEB_CONCURRENCY: 2" in compose
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "CELERY_ONBOARD_QUEUE" in AUTOMATION_FLAGS
    assert "ONBOARDING_PIPELINE" in AUTOMATION_FLAGS
    assert "FORM_BUILDER" in AUTOMATION_FLAGS
    assert "PROPOSAL_BUILDER" in AUTOMATION_FLAGS


def test_capacity_sheet_does_not_claim_50_day_live():
    text = (REPO / "docs" / "gtm" / "CAPACITY_50_DAY.md").read_text(encoding="utf-8")
    assert "Not a claim that 50/day is live" in text
    assert "WEB_CONCURRENCY=2" in text
    assert "CELERY_ONBOARD_QUEUE" in text


def test_phase1_stays_gated_and_dsh_star_allowlist_cannot_enable_all():
    phase1 = (REPO / "docs" / "gtm" / "PHASE1_GATED_RUNBOOK.md").read_text(encoding="utf-8")
    assert "Do **not** execute this until" in phase1
    import importlib
    import os

    dispatch_mod = importlib.import_module("app.platform.workforce_runtime.dispatch")

    assert dispatch_mod.FROZEN_AGENTS == frozenset({"swara", "ananya"})
    # "*" must collapse to empty, never "all agents"
    previous = os.environ.get("DSH_AGENT_ALLOWLIST")
    try:
        os.environ["DSH_AGENT_ALLOWLIST"] = "*"
        assert dispatch_mod._allowlist() == frozenset()
        assert dispatch_mod.provider_for("kavya") == "direct"
    finally:
        if previous is None:
            os.environ.pop("DSH_AGENT_ALLOWLIST", None)
        else:
            os.environ["DSH_AGENT_ALLOWLIST"] = previous
