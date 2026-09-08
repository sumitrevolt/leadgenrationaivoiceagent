"""Hot Queue auto-chase contracts — automated EMAIL follow-up on unactioned inquiry cards.

Inert-by-default (HQ_AUTO_CHASE off => zero work), email-only (WhatsApp/call stay
1-click human), idempotent per card, suppression-aware, fail-closed on SMTP missing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.platform import hq_auto_chase as hqc


def _run(coro):
    return asyncio.run(coro)


def _card(**over):
    base = {
        "channel": "inquiry",
        "from": "biz@test.in",
        "email": "biz@test.in",
        "business_name": "Test Biz",
        "phone": "9876543210",
        "at": (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(),
        "hq_status": "",
        "draft": "Namaste! inquiry draft",
    }
    base.update(over)
    return base


class _FakeSend:
    def __init__(self):
        self.calls = []

    async def __call__(self, to_email: str, body: str):
        self.calls.append((to_email, body))
        return True


def test_inert_when_flag_off(monkeypatch):
    """HQ_AUTO_CHASE unset => run_auto_chase returns disabled, no sends, no exceptions."""
    monkeypatch.delenv("HQ_AUTO_CHASE", raising=False)
    out = _run(hqc.run_auto_chase())
    assert out["enabled"] is False
    assert out.get("skip_reason") == "hq_auto_chase_disabled"


def test_skips_young_cards_and_phone_only(monkeypatch, tmp_path):
    monkeypatch.setenv("HQ_AUTO_CHASE", "1")
    monkeypatch.setenv("HQ_CHASE_HOURS", "24")
    monkeypatch.setattr(hqc, "logger", _NullLogger())

    fresh = _card(at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
    phone_only = _card(email="", phone="9876543210")
    drafts = [fresh, phone_only]

    monkeypatch.setattr("app.platform.reply_agent.list_drafts", lambda limit=50: drafts)
    monkeypatch.setattr("app.platform.reply_agent.hq_id_for", lambda row: "hq1")

    sent = []

    async def _send(to, body):  # pragma: no cover - should never be called
        sent.append(to)
        return True

    out = _run(hqc.run_auto_chase(send_fn=_send))
    assert out["enabled"] is True
    assert out["sent"] == 0
    assert out["skipped_not_due"] == 1
    assert out["skipped_phone_only"] == 1
    assert sent == []


def test_sends_email_to_unactioned_card_and_marks_sent(monkeypatch):
    monkeypatch.setenv("HQ_AUTO_CHASE", "1")
    monkeypatch.setenv("HQ_CHASE_HOURS", "24")
    card = _card()
    drafts = [card]
    updates = []

    monkeypatch.setattr("app.platform.reply_agent.list_drafts", lambda limit=50: drafts)
    monkeypatch.setattr("app.platform.reply_agent.hq_id_for", lambda row: "hq1")
    monkeypatch.setattr(
        "app.platform.reply_agent._update_draft_fields",
        lambda hq_id, u: updates.append((hq_id, u)),
    )
    fake = _FakeSend()

    out = _run(hqc.run_auto_chase(send_fn=fake))
    assert out["sent"] == 1
    assert out["ids"] == ["hq1"]
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == "biz@test.in"
    assert "₹1,999" in fake.calls[0][1]
    assert updates and updates[0][0] == "hq1"
    assert updates[0][1]["chase_status"] == "sent"


def test_skips_suppressed_recipient(monkeypatch):
    monkeypatch.setenv("HQ_AUTO_CHASE", "1")
    card = _card()
    drafts = [card]
    updates = []

    monkeypatch.setattr("app.platform.reply_agent.list_drafts", lambda limit=50: drafts)
    monkeypatch.setattr("app.platform.reply_agent.hq_id_for", lambda row: "hq1")
    monkeypatch.setattr(
        "app.platform.reply_agent._update_draft_fields",
        lambda hq_id, u: updates.append((hq_id, u)),
    )
    monkeypatch.setattr("app.platform.email_unsub.is_suppressed", lambda email: True)
    fake = _FakeSend()

    out = _run(hqc.run_auto_chase(send_fn=fake))
    assert out["skipped_suppressed"] == 1
    assert out["sent"] == 0
    assert fake.calls == []
    assert updates and updates[0][1]["chase_status"] == "blocked"


def test_skips_already_chased_and_done(monkeypatch):
    monkeypatch.setenv("HQ_AUTO_CHASE", "1")
    drafts = [
        _card(chase_status="sent", chased_at="2026-08-01T00:00:00Z"),
        _card(hq_status="done"),
    ]
    monkeypatch.setattr("app.platform.reply_agent.list_drafts", lambda limit=50: drafts)
    fake = _FakeSend()

    out = _run(hqc.run_auto_chase(send_fn=fake))
    # Both cards filtered before evaluation (already sent / done) — seen counts
    # only cards that pass the basic channel/status filters.
    assert out["sent"] == 0
    assert fake.calls == []


def test_daily_cap_respected(monkeypatch):
    monkeypatch.setenv("HQ_AUTO_CHASE", "1")
    monkeypatch.setenv("HQ_CHASE_DAILY_CAP", "1")
    drafts = [
        _card(**{"email": "a@test.in", "from": "a@test.in"}),
        _card(**{"email": "b@test.in", "from": "b@test.in"}),
    ]
    monkeypatch.setattr("app.platform.reply_agent.list_drafts", lambda limit=50: drafts)
    monkeypatch.setattr(
        "app.platform.reply_agent.hq_id_for", lambda row: "hq_" + str(row.get("email", ""))
    )
    monkeypatch.setattr("app.platform.reply_agent._update_draft_fields", lambda hq_id, u: None)
    fake = _FakeSend()

    out = _run(hqc.run_auto_chase(send_fn=fake))
    assert out["sent"] == 1
    assert len(fake.calls) == 1


def test_fail_closed_when_email_not_configured(monkeypatch):
    """SMTP missing => _send_chase_email returns False, never raises, counted failed."""
    monkeypatch.setenv("HQ_AUTO_CHASE", "1")

    class _NoCredsSender:
        user = ""
        password = ""

        async def send_email(self, *a, **k):  # pragma: no cover
            raise AssertionError("should not be called")

    monkeypatch.setattr("app.integrations.email_sender.EmailSender", _NoCredsSender)
    monkeypatch.setattr("app.integrations.email_api.api_available", lambda: False)
    monkeypatch.setattr("app.platform.email_unsub.headers_for", lambda email: {})

    ok = _run(hqc._send_chase_email("biz@test.in", "body"))
    assert ok is False


class _NullLogger:
    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass
