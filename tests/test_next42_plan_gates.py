"""Locks for the next42 plan: named blocker, never-arm flags, caps, hub inert."""

from __future__ import annotations

from pathlib import Path

from app.api.activation import _BLOCKER, _PROBES
from app.api.automation_flags import AUTOMATION_FLAGS
from app.config import Settings
from app.platform.automation_flag_manifest import FlagGovernance, describe_flag
from app.platform.coordination_hub_auth import hub_enabled

REPO = Path(__file__).resolve().parents[1]


def test_only_upi_pending_unactioned_can_be_a_blocker():
    """Public /summary blocker_count=1 has exactly one possible named key."""
    src = (REPO / "app" / "api" / "activation.py").read_text(encoding="utf-8")
    assert src.count('"status": _BLOCKER') == 1
    assert "_upi_pending_unactioned" in {fn.__name__ for fn in _PROBES}
    assert _BLOCKER == "BLOCKER"


def test_never_arm_flags_stay_owner_gated_or_safety():
    wa = describe_flag("SALES_AUTOPILOT_WHATSAPP_ENABLED")
    assert wa.governance == FlagGovernance.SAFETY_INVARIANT
    assert wa.default_hint in ("0", "")
    dunning = describe_flag("DUNNING_ENGINE")
    assert dunning.governance == FlagGovernance.OWNER_APPROVAL_REQUIRED
    harness = describe_flag("HARNESS_SESSION_EVENTS")
    assert harness.governance == FlagGovernance.CANARY_ONLY
    assert harness.default_hint == "0"
    hub = describe_flag("COORDINATION_HUB_ENABLED")
    assert hub.governance == FlagGovernance.CANARY_ONLY
    assert hub.default_hint == "0"


def test_coordination_hub_disabled_by_default(monkeypatch):
    monkeypatch.delenv("COORDINATION_HUB_ENABLED", raising=False)
    assert hub_enabled() is False


def test_gsc_and_onboard_and_watchdog_are_registered():
    for name in (
        "GSC_ENABLED",
        "AUTO_ONBOARD",
        "SIGNUP_AUTO_ONBOARD",
        "REPLY_AGENT",
        "JOURNEY_ENGINE",
        "CADENCE_ENGINE",
        "OPS_WATCHDOG",
        "AUTO_EMAIL_OUTREACH",
        "CELERY_ONBOARD_QUEUE",
    ):
        assert name in AUTOMATION_FLAGS, name


def test_outreach_daily_cap_defaults_to_50():
    # PR #365 on origin/main raised the shipped default; do not raise further here.
    assert Settings.model_fields["outreach_daily_cap"].default == 50


def test_web_concurrency_hardcoded_two_on_vps_compose():
    text = (REPO / "docker-compose.vps.yml").read_text(encoding="utf-8")
    assert "WEB_CONCURRENCY: 2" in text
    assert "mem_limit: 3g" in text


def test_inbox_and_start_routes_exist_in_main():
    text = (REPO / "app" / "main.py").read_text(encoding="utf-8")
    assert "/app/inbox" in text
    assert "/start" in text


def test_hot_queue_ntfy_and_upi_actionable_exist():
    """Shipped on origin/main via PR #363; this branch merged that ancestry."""
    ob = (REPO / "app" / "platform" / "office_briefing.py").read_text(encoding="utf-8")
    upi = (REPO / "app" / "platform" / "upi_payments.py").read_text(encoding="utf-8")
    api = (REPO / "app" / "api" / "upi_payments.py").read_text(encoding="utf-8")
    assert "async def _notify_owner_once" in ob
    assert "def list_actionable" in upi
    assert "list_actionable()" in api
