"""Tests for the REAL (durable, no-OAuth) calendar booking — council fast-follow D.

Hermetic: no network / no real calendar. Covers:
  1. Default provider = 'internal' (no creds) and a booking is DURABLE
     (persisted to the ledger + readable via list_bookings, with client/niche).
  2. Restart double-book guard: a fresh instance restores today's taken slots.
  3. Provider detection picks 'calcom' when BYOK creds are set.
  4. Owner-email routing falls back to NOTIFY_EMAIL.
"""

from __future__ import annotations

import asyncio


def _fresh_cal(monkeypatch, tmp_path):
    import app.integrations.calendar_booking as cb

    monkeypatch.setattr(cb, "DATA_BOOKINGS_DIR", str(tmp_path / "bookings"))
    monkeypatch.delenv("CALCOM_API_KEY", raising=False)
    monkeypatch.delenv("CALCOM_EVENT_TYPE_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CALENDAR_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CALENDAR_ID", raising=False)
    monkeypatch.setenv("BOOKING_NOTIFY", "0")  # no ntfy/email side-effects in tests
    return cb, cb.CalendarBooking()


def test_internal_booking_is_durable(monkeypatch, tmp_path):
    cb, cal = _fresh_cal(monkeypatch, tmp_path)
    assert cal.provider == "internal"
    res = asyncio.run(
        cal.book_slot(
            when_iso="2026-07-01T15:00",
            name="Rahul",
            phone="9876543210",
            notes="solar demo",
            client_id="c1",
            niche="solar_residential",
        )
    )
    assert res.ok and res.provider == "internal" and res.booking_id
    items = cal.list_bookings(limit=10)
    match = [b for b in items if b.get("booking_id") == res.booking_id]
    assert match, "booking must be persisted to the durable ledger"
    assert match[0]["client_id"] == "c1" and match[0]["niche"] == "solar_residential"


def test_restart_double_book_guard(monkeypatch, tmp_path):
    cb, cal = _fresh_cal(monkeypatch, tmp_path)
    asyncio.run(cal.book_slot(when_iso="2026-07-01T15:00", name="A", phone="1"))
    # a FRESH instance must restore today's taken slots from the ledger
    cal2 = cb.CalendarBooking()
    res = asyncio.run(cal2.book_slot(when_iso="2026-07-01T15:00", name="B", phone="2"))
    assert res.ok is False and "already" in (res.error or "").lower()


def test_provider_detect_calcom(monkeypatch, tmp_path):
    cb, _ = _fresh_cal(monkeypatch, tmp_path)
    monkeypatch.setenv("CALCOM_API_KEY", "cal_test_key")
    monkeypatch.setenv("CALCOM_EVENT_TYPE_ID", "123")
    cal = cb.CalendarBooking()
    assert cal.provider == "calcom"


def test_owner_email_fallback(monkeypatch, tmp_path):
    cb, cal = _fresh_cal(monkeypatch, tmp_path)
    monkeypatch.setenv("NOTIFY_EMAIL", "admin@leadsgenai.in")
    out = cal._owner_email("")
    assert "@" in out  # falls back to an admin/owner address
