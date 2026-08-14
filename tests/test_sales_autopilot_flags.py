"""Sales Autopilot — flags default OFF + calling stays HARD OFF."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    from app.platform.sales_autopilot import policy

    # Isolate from both env and the local data file.
    monkeypatch.setattr(policy, "_read_file", lambda: {})
    for k in (
        "SALES_AUTOPILOT_ENABLED",
        "SALES_AUTOPILOT_WHATSAPP_ENABLED",
        "SALES_AUTOPILOT_EMAIL_ENABLED",
        "SALES_AUTOPILOT_DRY_RUN",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


def test_flags_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS

    for f in (
        "SALES_AUTOPILOT_ENABLED",
        "SALES_AUTOPILOT_WHATSAPP_ENABLED",
        "SALES_AUTOPILOT_EMAIL_ENABLED",
    ):
        assert f in AUTOMATION_FLAGS


def test_whatsapp_auto_send_not_reused_as_master(monkeypatch):
    """WHATSAPP_AUTO_SEND must NOT arm the autopilot engine."""
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    from app.platform.sales_autopilot import policy

    pol = policy.get_policy()
    assert pol.enabled is False  # master gate is SALES_AUTOPILOT_ENABLED only


def test_policy_defaults_safe():
    from app.platform.sales_autopilot import policy

    pol = policy.get_policy()
    assert pol.enabled is False
    assert pol.dry_run is True  # disabled ⇒ always dry-run
    assert pol.get("whatsapp_enabled") is False
    assert pol.get("email_enabled") is False
    assert pol.canary_batch() == 1
    assert pol.max_followups() == 2


def test_calling_hard_off_summary_marker():
    """The engine never exposes a calling-enable; summary marks HARD OFF."""
    from app.platform.sales_autopilot import scheduler

    # scheduler exposes only run_tick; no dial/call symbol exists.
    assert not hasattr(scheduler, "dial")
    assert not hasattr(scheduler, "call")
