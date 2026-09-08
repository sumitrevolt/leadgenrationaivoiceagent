"""Tests: post-call AI summary wiring into auto_qualify_and_downstream.

Covers:
  - qualified call → send_post_call_summary called with qualifier + context
  - NOT qualified → no summary send
  - POST_CALL_SUMMARY flag OFF → send skipped (formatter gate)
  - flag registry documents POST_CALL_SUMMARY
"""

from __future__ import annotations

import pytest

from app.telephony import post_call_hooks


def _make_hist() -> list[dict[str, str]]:
    return [
        {"role": "assistant", "content": "Namaste! Main [Company] se bol rahi hoon."},
        {"role": "user", "content": "Haan, batao."},
        {"role": "assistant", "content": "Aap demo lena chahenge?"},
        {"role": "user", "content": "Haan bilkul, kal ka time de do."},
        {"role": "assistant", "content": "Theek hai, kal 3 baje demo fix."},
        {"role": "user", "content": "Perfect, thank you."},
    ]


async def _run_auto_qualify(monkeypatch, *, qualified: bool, summary_flag: str = "0"):
    """Run auto_qualify_and_downstream with monkeypatched qualifier + summary sender."""
    monkeypatch.setenv("AUTO_QUALIFY_CALLS", "1")
    monkeypatch.setenv("POST_CALL_SUMMARY", summary_flag)
    monkeypatch.delenv("WHATSAUTO_SEND", raising=False)

    calls: list[dict] = []

    async def _fake_qualify(txt, context=None):
        return {
            "interest_score": 4 if qualified else 1,
            "qualified": qualified,
            "appointment_requested": False,
            "budget_signal": "medium",
            "summary": "Lead ne demo book kiya.",
            "next_action": "Kal 3 baje demo call.",
            "followup_draft": "Namaste! Demo confirm hai.",
        }

    async def _fake_send(qualifier, **kw):
        calls.append({"qualifier": qualifier, **kw})
        return {"ok": True, "message_id": "wamid_x"}

    # Function-level imports: patch source modules, not post_call_hooks namespace.
    import app.voice_agent.call_qualifier as cq_mod

    monkeypatch.setattr(cq_mod, "qualify_transcript", _fake_qualify)
    monkeypatch.setattr("app.voice_agent.call_summary_formatter.send_post_call_summary", _fake_send)

    q = await post_call_hooks.auto_qualify_and_downstream(
        _make_hist(),
        call_id="call_xyz",
        client_id="client_abc",
        client_name="Test Salon",
        phone="919999000001",
        niche="salon_spa",
        call_duration_s=95.0,
    )
    return q, calls


@pytest.mark.asyncio
async def test_qualified_call_sends_summary(monkeypatch):
    q, calls = await _run_auto_qualify(monkeypatch, qualified=True, summary_flag="1")
    assert q is not None and q.get("qualified") is True
    assert len(calls) == 1
    kw = calls[0]
    assert kw["phone"] == "919999000001"
    assert kw["client_name"] == "Test Salon"
    assert kw["niche"] == "salon_spa"
    assert kw["call_duration_s"] == 95.0
    assert kw["call_id"] == "call_xyz"
    assert kw["qualifier"]["summary"] == "Lead ne demo book kiya."


@pytest.mark.asyncio
async def test_not_qualified_skips_summary(monkeypatch):
    q, calls = await _run_auto_qualify(monkeypatch, qualified=False, summary_flag="1")
    assert q is not None and q.get("qualified") is False
    assert calls == []


@pytest.mark.asyncio
async def test_summary_flag_off_skips_send(monkeypatch):
    q, calls = await _run_auto_qualify(monkeypatch, qualified=True, summary_flag="0")
    assert q is not None
    # send_post_call_summary called but its own gate blocks (returns reason)
    assert len(calls) == 1
    assert calls[0]["qualifier"]["qualified"] is True


def test_flag_registered_in_manifest():
    from app.platform import automation_flag_manifest as afm

    desc = afm.describe_flag("POST_CALL_SUMMARY")
    assert desc is not None
    assert desc.name == "POST_CALL_SUMMARY"


def test_formatter_requires_flag():
    from app.voice_agent import call_summary_formatter as f

    assert f._enabled() is False  # default OFF


@pytest.mark.asyncio
async def test_formatter_send_skips_when_disabled(monkeypatch):
    from app.voice_agent import call_summary_formatter as f

    monkeypatch.delenv("POST_CALL_SUMMARY", raising=False)
    res = await f.send_post_call_summary(
        {"interest_score": 4, "qualified": True}, phone="919999000001"
    )
    assert res["ok"] is False
    assert "disabled" in res["reason"]


@pytest.mark.asyncio
async def test_formatter_send_skips_low_score(monkeypatch):
    from app.voice_agent import call_summary_formatter as f

    monkeypatch.setenv("POST_CALL_SUMMARY", "1")

    async def _fake_sender(phone, msg):
        raise AssertionError("should not send for unqualified call")

    monkeypatch.setattr(
        "app.integrations.whatsapp.get_whatsapp_sender",
        lambda: type("S", (), {"send_text_message": _fake_sender})(),
    )
    res = await f.send_post_call_summary(
        {"interest_score": 0, "qualified": False}, phone="919999000001"
    )
    assert res["ok"] is False
    assert "skip" in res["reason"]


@pytest.mark.asyncio
async def test_formatter_sends_qualified(monkeypatch):
    from app.voice_agent import call_summary_formatter as f

    monkeypatch.setenv("POST_CALL_SUMMARY", "1")
    sent: list[str] = []

    class _FakeSender:
        async def send_text_message(self, phone, msg):
            sent.append((phone, msg))
            return {"messages": [{"id": "wamid_1"}]}

    # get_whatsapp_sender is imported INSIDE send_post_call_summary — patch the
    # source module where the import resolves (app.integrations.whatsapp).
    monkeypatch.setattr(
        "app.integrations.whatsapp.get_whatsapp_sender",
        lambda: _FakeSender(),
    )
    res = await f.send_post_call_summary(
        {
            "interest_score": 4,
            "qualified": True,
            "appointment_requested": True,
            "budget_signal": "medium",
            "summary": "Demo booked kal 3 baje.",
            "next_action": "Confirm demo call.",
        },
        phone="919999000001",
        client_name="Glow Salon",
        niche="salon_spa",
        call_duration_s=90.0,
    )
    assert res["ok"] is True
    assert len(sent) == 1
    phone, msg = sent[0]
    assert phone == "919999000001"
    assert "Demo booked kal 3 baje." in msg
    assert "APPOINTMENT REQUESTED" in msg
    assert "Glow Salon" in msg
