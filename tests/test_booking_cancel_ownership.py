"""Contract for booking-cancel possession factor (audit 2026-07-06, 2nd-pass sec fix).

`/booking/cancel` used to cancel on booking_id ALONE — a leaked/guessed id could
cancel someone else's appointment. `cancel()` now requires the caller's phone to
match the booking's stored phone (last-10). Internal callers (reschedule) pass no
phone and stay unaffected.
"""

from app.integrations.calendar_booking import CalendarBooking


def _seed(cal, bid="bk_test123", phone="9876543210"):
    cal._bookings[bid] = {
        "event_id": bid,
        "when": "2026-08-01T10:00:00",
        "name": "Asha",
        "phone": phone,
        "client_id": "c1",
    }
    return bid


async def test_wrong_phone_refused_and_booking_survives():
    cal = CalendarBooking(provider=None)
    bid = _seed(cal)
    assert await cal.cancel(bid, phone="1111111111") is False
    assert bid in cal._bookings  # not cancelled


async def test_correct_phone_cancels():
    cal = CalendarBooking(provider=None)
    bid = _seed(cal)
    assert await cal.cancel(bid, phone="9876543210") is True
    assert bid not in cal._bookings


async def test_last10_match_ignores_formatting():
    cal = CalendarBooking(provider=None)
    bid = _seed(cal, phone="+91 98765 43210")
    assert await cal.cancel(bid, phone="098765-43210") is True  # last-10 digits match


async def test_internal_caller_no_phone_still_cancels():
    # reschedule() calls self.cancel(old_bid) with no phone — must keep working
    cal = CalendarBooking(provider=None)
    bid = _seed(cal)
    assert await cal.cancel(bid) is True
    assert bid not in cal._bookings


async def test_unknown_id_returns_false():
    cal = CalendarBooking(provider=None)
    assert await cal.cancel("bk_does_not_exist", phone="9876543210") is False
