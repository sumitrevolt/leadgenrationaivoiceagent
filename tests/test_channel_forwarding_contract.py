"""OPS-023 — pin the channel-forwarding contract with BEHAVIOURAL tests.

Why this file exists
--------------------
OPS-022: a concurrent worker silently removed a compliance-gate edit from
``app/telephony/compliance.py`` mid-cycle. The suite caught it — but only by
accident, because four unrelated tests happened to depend on the fallback.

Auditing what would NOT have been caught: nothing pinned that the call sites
actually FORWARD ``channel=`` to the DND checker. Delete ``channel="voice"``
from ``compliance.py`` and every test still goes green — while voice silently
loses its carrier-scrub allowance and the cold-call path quietly goes
fail-closed. Delete the strictest-channel logic from
``orchestrator_pipeline.py`` and stage 5 would WhatsApp-blast leads that were
only ever cleared for a call. Both are silent, and both are compliance-shaped.

These tests pin the contract by RECORDING what the checker was asked, not by
scraping source text — so they survive refactors and still fail on a revert.

THESE TESTS ARE A COMPLIANCE GATE. If any fail, do NOT "fix" them by loosening
an assertion — find out which call site stopped declaring its channel.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time

import pytest

from app.automation.orchestrator_pipeline import CampaignResult, LeadGenPipeline
from app.telephony.compliance import IST, CallType, ComplianceGate


class RecordingChecker:
    """DND stand-in that records the channel it was asked about."""

    def __init__(self, verified: bool = True, is_dnd: bool = False):
        self.verified = verified
        self.is_dnd = is_dnd
        self.calls: list[tuple[str, str | None]] = []

    async def check_single(self, phone: str, channel: str | None = None):
        self.calls.append((phone, channel))
        return type(
            "R", (), {"is_dnd": self.is_dnd, "verified": self.verified}
        )()


# ------------------------------------------------------------ voice path


def test_compliance_gate_forwards_voice_channel():
    """Voice must declare voice — it is the ONLY channel carrier scrub clears."""
    checker = RecordingChecker()
    gate = ComplianceGate(dnd_checker=checker)
    asyncio.run(
        gate.check(
            "+919876543210",
            CallType.PROMOTIONAL,
            now=datetime(2026, 6, 7, 12, 0, tzinfo=IST),
        )
    )
    assert checker.calls, "compliance gate never consulted the DND checker"
    assert all(ch == "voice" for _phone, ch in checker.calls), (
        f"compliance must scrub as voice, got {checker.calls}"
    )


def test_transactional_call_does_not_consult_the_dnd_registry():
    """Documents the contract: DND scrubbing is a PROMOTIONAL obligation.

    If this ever starts firing for transactional traffic, someone widened the
    gate — check why before changing the assertion.
    """
    checker = RecordingChecker()
    gate = ComplianceGate(dnd_checker=checker)
    asyncio.run(
        gate.check(
            "+919876543210",
            CallType.TRANSACTIONAL,
            now=datetime(2026, 6, 7, 12, 0, tzinfo=IST),
        )
    )
    assert checker.calls == []


# ------------------------------------------------------ pipeline stage 3


def _scrub_with(channels):
    pipeline = LeadGenPipeline()
    checker = RecordingChecker(verified=True, is_dnd=False)
    pipeline.dnd_checker = checker
    leads = [type("L", (), {"phone": "+919876543210"})()]
    result = CampaignResult(client_id="c1", niche="solar")
    asyncio.run(pipeline._stage_dnd_scrub(leads, result, channels=channels))
    return [ch for _p, ch in checker.calls]


def test_pipeline_scrubs_messaging_when_whatsapp_enabled():
    """Stage 5 (WhatsApp warm-up) shares this scrub — so it must be the strict one."""
    for channels in (["whatsapp", "voice"], ["whatsapp"], None):
        seen = _scrub_with(channels)
        assert seen, f"no DND lookup performed for channels={channels}"
        assert all(ch == "messaging" for ch in seen), (
            f"channels={channels} must scrub as messaging, got {seen}"
        )


def test_pipeline_scrubs_voice_only_for_a_voice_only_run():
    seen = _scrub_with(["voice"])
    assert seen == ["voice"], f"voice-only run must scrub as voice, got {seen}"


def test_pipeline_strict_channel_is_the_default_channels_constant():
    """The documented default channels=['whatsapp','voice'] must scrub strict."""
    seen = _scrub_with(["whatsapp", "voice"])
    assert set(seen) == {"messaging"}


# ------------------------------------------------------- messaging path


def test_whatsapp_automation_forwards_messaging_channel(monkeypatch):
    import app.tasks.whatsapp_automation as wa
    import app.utils.dnd_checker as dc

    checker = RecordingChecker(verified=True, is_dnd=False)
    monkeypatch.setattr(dc, "DNDChecker", lambda: checker)
    kept, blocked = wa._run_async(wa._scrub_dnd([{"phone": "+919876543210"}]))
    assert checker.calls, "WA automation never consulted the DND checker"
    assert all(ch == "messaging" for _p, ch in checker.calls), (
        f"WA automation must scrub as messaging, got {checker.calls}"
    )
    assert len(kept) == 1 and blocked == 0


# --------------------------------------------------------- the constants


def test_carrier_scrub_allowlist_is_voice_only():
    from app.utils.dnd_checker import CARRIER_SCRUB_CHANNELS, DEFAULT_CHANNEL

    assert CARRIER_SCRUB_CHANNELS == {"voice"}
    assert DEFAULT_CHANNEL == "messaging"
    assert DEFAULT_CHANNEL not in CARRIER_SCRUB_CHANNELS


def test_check_single_accepts_channel_and_defaults_strict():
    import inspect

    from app.utils.dnd_checker import DNDChecker

    sig = inspect.signature(DNDChecker.check_single)
    assert "channel" in sig.parameters
    assert sig.parameters["channel"].default == "messaging"


def test_promotional_window_constants_unchanged():
    """Guard rail: these are legal ceilings, not tunables."""
    from app.automation.orchestrator_pipeline import CALL_WINDOW_END, CALL_WINDOW_START

    assert CALL_WINDOW_START == time(9, 0)
    assert CALL_WINDOW_END == time(21, 0)


@pytest.mark.parametrize("channels", [["whatsapp", "voice"], ["voice"], None, []])
def test_pipeline_never_leaves_channel_unset(channels):
    seen = _scrub_with(channels)
    assert seen
    assert all(ch in ("voice", "messaging") for ch in seen), seen
