"""P3a (2026-06-28): reschedule flow in calendar_booking — find existing by phone
(durable ledger), free old slot, book new. Plus the voice-tool registration.
"""

from __future__ import annotations

import asyncio


def test_reschedule_frees_old_books_new(tmp_path, monkeypatch):
    import app.integrations.calendar_booking as cb

    monkeypatch.setattr(cb, "DATA_BOOKINGS_DIR", str(tmp_path / "bookings"))
    monkeypatch.setattr(cb, "_booking_notify_enabled", lambda: False)  # no ntfy/email in test
    cal = cb.CalendarBooking(provider="internal")

    r1 = asyncio.run(cal.book_slot("2026-07-01T11:00", name="Sumit", phone="9876501234"))
    assert r1.ok and "2026-07-01T11:00:00" in cal._taken

    r2 = asyncio.run(cal.reschedule(new_when_iso="2026-07-02T15:00", phone="98765 01234"))
    assert r2.ok
    assert "2026-07-02T15:00:00" in cal._taken  # new slot taken
    assert "2026-07-01T11:00:00" not in cal._taken  # old slot freed
    assert "move" in r2.confirmation_text.lower()
    assert r2.meta.get("rescheduled_from") == "2026-07-01T11:00:00"


def test_reschedule_bad_time_is_graceful(tmp_path, monkeypatch):
    import app.integrations.calendar_booking as cb

    monkeypatch.setattr(cb, "DATA_BOOKINGS_DIR", str(tmp_path / "bookings"))
    cal = cb.CalendarBooking(provider="internal")
    r = asyncio.run(cal.reschedule(new_when_iso="not-a-time", phone="9876501234"))
    assert r.ok is False and r.confirmation_text


def test_reschedule_tool_registered():
    from app.voice_agent.function_calling import build_default_registry

    reg = build_default_registry({"niche": "ai_marketing"})
    assert "reschedule_appointment" in reg.names()
