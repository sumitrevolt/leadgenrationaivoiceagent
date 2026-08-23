"""Per-client appointment-slot scoping — regression for the shared-singleton bug.

AUDIT BUG: the slot pool (`_taken`) was a single process-wide set, so a slot booked
on one business's mini-site (e.g. "jiya makeover") blocked that exact wall-clock slot
for EVERY other business. Fix scopes availability + the double-book guard per client
via `_slot_key(client_id, when_iso)`.

Hermetic: no network / no real calendar (internal durable-ledger provider). Covers:
  1. Same slot bookable by TWO different clients (the reported bug).
  2. Double-book same slot + same client -> rejected.
  3. No-client (legacy/global) booking still guards itself; legacy ledger rows
     (rows WITHOUT a client_id) load without crash and stay global-only — they do
     NOT poison a per-client bucket.
  4. Availability is per-client (a slot taken by one client is still offered to another).
  5. API layer: slug -> client_id resolution isolates two mini-sites.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta


def _fresh_cal(monkeypatch, tmp_path):
    """A CalendarBooking on the internal (no-creds) provider, ledger -> tmp_path."""
    import app.integrations.calendar_booking as cb

    monkeypatch.setattr(cb, "DATA_BOOKINGS_DIR", str(tmp_path / "bookings"))
    monkeypatch.delenv("CALCOM_API_KEY", raising=False)
    monkeypatch.delenv("CALCOM_EVENT_TYPE_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CALENDAR_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CALENDAR_ID", raising=False)
    monkeypatch.setenv("BOOKING_NOTIFY", "0")  # no ntfy/email side-effects in tests
    return cb, cb.CalendarBooking()


def _next_weekday_at(hour: int = 11) -> str:
    """A FUTURE Mon-Sat slot ISO (availability skips past slots + Sundays)."""
    d = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=2)
    while d.weekday() == 6:  # Sunday closed
        d += timedelta(days=1)
    return d.replace(hour=hour).isoformat()


# --------------------------------------------------------------------------- #
# 1. Same slot bookable by two DIFFERENT clients (the reported bug).
# --------------------------------------------------------------------------- #
def test_same_slot_two_clients_both_succeed(monkeypatch, tmp_path):
    cb, cal = _fresh_cal(monkeypatch, tmp_path)
    when = "2026-07-01T15:00"  # fixed past date: internal book has no past-date guard
    r1 = asyncio.run(cal.book_slot(when_iso=when, name="Jiya cust", phone="1", client_id="jiya"))
    r2 = asyncio.run(cal.book_slot(when_iso=when, name="Tattoo cust", phone="2", client_id="trend"))
    assert r1.ok, r1.error
    assert r2.ok, f"different client must be able to hold the SAME slot; got: {r2.error}"
    assert r1.booking_id != r2.booking_id


# --------------------------------------------------------------------------- #
# 2. Double-book same slot + same client -> rejected.
# --------------------------------------------------------------------------- #
def test_double_book_same_client_rejected(monkeypatch, tmp_path):
    cb, cal = _fresh_cal(monkeypatch, tmp_path)
    when = "2026-07-01T15:00"
    r1 = asyncio.run(cal.book_slot(when_iso=when, name="A", phone="1", client_id="jiya"))
    r2 = asyncio.run(cal.book_slot(when_iso=when, name="B", phone="2", client_id="jiya"))
    assert r1.ok
    assert r2.ok is False and "already" in (r2.error or "").lower()


# --------------------------------------------------------------------------- #
# 3. No-client (global) booking guards itself + a per-client book at the same
#    wall-clock time is unaffected (buckets are separate).
# --------------------------------------------------------------------------- #
def test_global_and_client_buckets_are_separate(monkeypatch, tmp_path):
    cb, cal = _fresh_cal(monkeypatch, tmp_path)
    when = "2026-07-01T16:00"
    g1 = asyncio.run(cal.book_slot(when_iso=when, name="G", phone="1"))  # no client_id
    g2 = asyncio.run(cal.book_slot(when_iso=when, name="G2", phone="2"))  # global dup
    c1 = asyncio.run(cal.book_slot(when_iso=when, name="C", phone="3", client_id="jiya"))
    assert g1.ok
    assert g2.ok is False and "already" in (g2.error or "").lower()  # global self-guards
    assert c1.ok, "a per-client book must NOT be blocked by a global/legacy booking"


# --------------------------------------------------------------------------- #
# 4. Legacy ledger rows (no client_id) load fine + stay global-only.
# --------------------------------------------------------------------------- #
def test_legacy_rows_load_and_do_not_poison_client_buckets(monkeypatch, tmp_path):
    cb, _ = _fresh_cal(monkeypatch, tmp_path)
    ledger_dir = tmp_path / "bookings"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")  # ledger files keyed by booked-at
    # Canonical isoformat as a REAL persisted booking stores it (result.when =
    # normalized dt.isoformat() -> seconds present). This is what a genuine pre-scoping
    # (legacy) row looks like; only the client_id key is absent.
    legacy_iso = "2026-07-01T17:00:00"
    # A legacy row: NO client_id key at all (pre-scoping format).
    legacy_row = {
        "booking_id": "bk_legacy0001",
        "when": legacy_iso,
        "provider": "internal",
        "name": "Old lead",
        "phone": "9998887770",
        "booked_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(os.path.join(str(ledger_dir), today + ".jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps(legacy_row) + "\n")

    # (a) fresh instance loads the legacy row WITHOUT crashing.
    cal = cb.CalendarBooking()
    assert cal.provider == "internal"

    # (b) a NO-client booking at that iso is rejected (legacy is global).
    g = asyncio.run(cal.book_slot(when_iso=legacy_iso, name="X", phone="1"))
    assert g.ok is False and "already" in (g.error or "").lower()

    # (c) a per-client booking at that same iso SUCCEEDS (legacy didn't poison it).
    c = asyncio.run(cal.book_slot(when_iso=legacy_iso, name="Jiya", phone="2", client_id="jiya"))
    assert c.ok, "legacy global row must not block a per-client slot of the same time"


# --------------------------------------------------------------------------- #
# 5. Availability is per-client: a slot taken by one client is still offered to
#    another (and hidden for the client who took it).
# --------------------------------------------------------------------------- #
def test_availability_is_per_client(monkeypatch, tmp_path):
    cb, cal = _fresh_cal(monkeypatch, tmp_path)
    when = _next_weekday_at(11)
    day = when.split("T")[0]
    booked = asyncio.run(cal.book_slot(when_iso=when, name="J", phone="1", client_id="jiya"))
    assert booked.ok, booked.error

    jiya_slots = asyncio.run(cal.check_availability(day, duration_min=30, client_id="jiya"))
    trend_slots = asyncio.run(cal.check_availability(day, duration_min=30, client_id="trend"))
    assert when not in jiya_slots, "the client who booked should NOT see their own taken slot"
    assert when in trend_slots, "another client must still be offered that wall-clock slot"


# --------------------------------------------------------------------------- #
# 6. API layer: slug -> client_id resolution isolates two mini-sites.
# --------------------------------------------------------------------------- #
def test_api_resolve_client_id_from_slug(monkeypatch, tmp_path):
    import app.api.booking as bk

    # get_by_slug found -> owning client id; not-found -> slug fallback (still isolates).
    monkeypatch.setattr(
        "app.marketing.clients_store.get_by_slug",
        lambda slug: {"id": "d79d690f61b3"} if slug == "jiya-makeover" else None,
    )
    assert bk._resolve_client_id("jiya-makeover") == "d79d690f61b3"
    assert bk._resolve_client_id("unknown-slug") == "unknown-slug"  # fallback isolates
    assert bk._resolve_client_id("") == ""


def test_api_book_scopes_by_slug(monkeypatch, tmp_path):
    """Two mini-sites booking the same slot via the /book handler both succeed."""
    import app.api.booking as bk
    import app.integrations.calendar_booking as cb

    monkeypatch.setattr(cb, "DATA_BOOKINGS_DIR", str(tmp_path / "bookings"))
    monkeypatch.setenv("BOOKING_NOTIFY", "0")
    for k in (
        "CALCOM_API_KEY",
        "CALCOM_EVENT_TYPE_ID",
        "GOOGLE_CALENDAR_CREDENTIALS",
        "GOOGLE_CALENDAR_ID",
    ):
        monkeypatch.delenv(k, raising=False)
    # reset the module singleton so it picks up the patched ledger dir
    monkeypatch.setattr(cb, "_calendar", None, raising=False)
    # slug maps 1:1 to a distinct client_id (no clients_store dependency)
    monkeypatch.setattr(bk, "_resolve_client_id", lambda slug: (slug or "").strip())

    when = "2026-07-01T18:00"
    r1 = asyncio.run(bk.book_slot(bk.BookIn(slot=when, name="J", phone="9998887771", slug="jiya")))
    r2 = asyncio.run(bk.book_slot(bk.BookIn(slot=when, name="T", phone="9998887772", slug="trend")))
    assert r1.get("ok") is True, r1
    assert r2.get("ok") is True, r2  # different slug/client -> same slot ok
    # same slug again -> rejected (double-book guard per client)
    r3 = asyncio.run(bk.book_slot(bk.BookIn(slot=when, name="J2", phone="9998887773", slug="jiya")))
    assert r3.get("ok") is False and "already" in (r3.get("error") or "").lower()
