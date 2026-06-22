"""
Calendar Booking Integration
============================

Appointment booking + availability checking for the AI voice agent — yeh wahi
"in-call action" feature hai jo Retell/Vapi/Bland dete hain: agent call ke
beech me hi slot dekh ke meeting book kar deta hai.

Provider selection (priority order):
    1. Google Calendar — agar service-account creds present hain
       (settings.google_sheets_credentials reuse, ya GOOGLE_CALENDAR_CREDENTIALS).
    2. Else -> in-memory SIMULATION mode: business hours Mon-Sat 10:00-18:00 IST
       me free slots generate karke book karta hai (no keys needed).

Design goals (telephony_service.py jaisa):
    - import-safe: import ya init pe kabhi crash nahi (SDK/keys missing hon to bhi).
    - defensive: har provider error gracefully degrade hota hai (logged), caller
      ko hamesha ek BookingResult / list-of-slots milta hai.
    - env-gated: keys nahi to seedha simulation.

Usage:
    from app.integrations.calendar_booking import get_calendar

    cal = get_calendar()
    slots = await cal.check_availability("2026-06-10", duration_min=15)
    res = await cal.book_slot(slots[0], name="Rahul", phone="9876543210",
                              notes="Solar demo")
    # res -> BookingResult(ok, booking_id, when, confirmation_text)
    await cal.cancel(res.booking_id)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import time as dtime
from typing import Any

try:
    from app.config import settings
except Exception:  # pragma: no cover - keep import-safe
    settings = None  # type: ignore

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Business-hours config (IST). Mon-Sat 10:00-18:00, slot-grid based.
# --------------------------------------------------------------------------- #
BUSINESS_DAYS = {0, 1, 2, 3, 4, 5}  # Mon=0 ... Sat=5 (Sun=6 closed)
BUSINESS_START = dtime(10, 0)
BUSINESS_END = dtime(18, 0)
DEFAULT_DURATION_MIN = 15


@dataclass
class BookingResult:
    """Unified result for a booking attempt."""

    ok: bool
    booking_id: str | None = None
    when: str | None = None  # ISO 8601 start time
    confirmation_text: str = ""
    provider: str = "simulation"
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _setting(name: str, default: str = "") -> str:
    """Read from settings (lowercased) first, then raw env. Stripped str."""
    val = None
    if settings is not None:
        val = getattr(settings, name.lower(), None)
    if val is None or val == "":
        val = os.getenv(name, default)
    return (val or "").strip()


class CalendarBooking:
    """
    Calendar service facade for the voice agent.

    Uses Google Calendar when credentials exist; otherwise an in-memory slot
    book that mimics a real calendar so the whole pipeline works key-free.
    """

    def __init__(self, provider: str | None = None):
        # In-memory booking book: booking_id -> record (used in simulation and
        # also as a local mirror for fast cancels).
        self._bookings: dict[str, dict[str, Any]] = {}
        # when-ISO set, to avoid double-booking the same slot in simulation.
        self._taken: set = set()

        self.provider = (provider or self._detect_provider()).lower()
        self._gcal = None  # lazily built Google Calendar service

        if self.provider == "google":
            try:
                self._gcal = self._build_google_calendar()
                if self._gcal is None:
                    self.provider = "simulation"
            except Exception as e:
                logger.error(f"Google Calendar init failed ({e}); using simulation.")
                self.provider = "simulation"

        if self.provider == "simulation":
            logger.info(
                "📅 CalendarBooking in SIMULATION mode — no calendar keys needed. "
                "Slots: Mon-Sat 10:00-18:00 IST."
            )
        else:
            logger.info(f"📅 CalendarBooking active provider: {self.provider}")

    # ------------------------------------------------------------------ #
    # Provider detection / construction
    # ------------------------------------------------------------------ #
    def _detect_provider(self) -> str:
        """Pick 'google' if creds exist, else 'simulation'."""
        creds = _setting("GOOGLE_CALENDAR_CREDENTIALS") or _setting("google_sheets_credentials")
        cal_id = _setting("GOOGLE_CALENDAR_ID")
        if creds and os.path.exists(creds) and cal_id:
            return "google"
        return "simulation"

    def _build_google_calendar(self):
        """Build a Google Calendar API service. Local imports keep us safe if
        the google libs are not installed."""
        creds_path = _setting("GOOGLE_CALENDAR_CREDENTIALS") or _setting(
            "google_sheets_credentials"
        )
        self._calendar_id = _setting("GOOGLE_CALENDAR_ID") or "primary"
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            scopes = ["https://www.googleapis.com/auth/calendar"]
            credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
            service = build("calendar", "v3", credentials=credentials)
            logger.info("📅 Google Calendar service constructed")
            return service
        except ImportError:
            logger.warning(
                "google-api-python-client not installed; calendar -> simulation. "
                "Run: pip install google-api-python-client"
            )
            return None
        except Exception as e:
            logger.error(f"Google Calendar build error: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def check_availability(
        self,
        date_str: str,
        duration_min: int = DEFAULT_DURATION_MIN,
    ) -> list[str]:
        """
        Return a list of free slot start-times (ISO 8601) for the given date.

        Args:
            date_str:     "YYYY-MM-DD" (e.g. "2026-06-10"). Invalid/empty ->
                          next business day.
            duration_min: meeting length in minutes (grid step).

        Never raises — on any failure returns the simulated free slots so the
        agent can still offer something.
        """
        day = self._parse_date(date_str)
        duration_min = max(5, int(duration_min or DEFAULT_DURATION_MIN))

        if self.provider == "google" and self._gcal is not None:
            try:
                return await self._google_free_slots(day, duration_min)
            except Exception as e:
                logger.error(f"Google availability failed ({e}); simulating.")

        return self._sim_free_slots(day, duration_min)

    async def book_slot(
        self,
        when_iso: str,
        name: str,
        phone: str,
        notes: str = "",
        duration_min: int = DEFAULT_DURATION_MIN,
    ) -> BookingResult:
        """
        Book an appointment at `when_iso` for `name` / `phone`.

        Never raises — returns BookingResult(ok=False, error=...) on failure.
        """
        when = self._normalize_when(when_iso)
        if not when:
            return BookingResult(
                ok=False,
                provider=self.provider,
                error=f"Invalid start time: {when_iso!r}",
                confirmation_text="Sorry, woh time samajh nahi aaya — dobara batayein?",
            )

        duration_min = max(5, int(duration_min or DEFAULT_DURATION_MIN))

        if self.provider == "google" and self._gcal is not None:
            try:
                return await self._google_book(when, name, phone, notes, duration_min)
            except Exception as e:
                logger.error(f"Google booking failed ({e}); simulating.")

        return self._sim_book(when, name, phone, notes, duration_min)

    async def cancel(self, booking_id: str) -> bool:
        """Cancel a booking. Never raises; returns True if cancelled."""
        if not booking_id:
            return False

        record = self._bookings.get(booking_id)
        if self.provider == "google" and self._gcal is not None and record:
            try:
                await asyncio.to_thread(
                    self._gcal.events()
                    .delete(
                        calendarId=getattr(self, "_calendar_id", "primary"),
                        eventId=record.get("event_id", booking_id),
                    )
                    .execute
                )
            except Exception as e:
                logger.error(f"Google cancel failed ({e}); removing local mirror.")

        if record:
            self._taken.discard(record.get("when"))
            self._bookings.pop(booking_id, None)
            logger.info(f"📅 Cancelled booking {booking_id}")
            return True

        logger.warning(f"Cancel: booking_id {booking_id} not found.")
        return False

    # ------------------------------------------------------------------ #
    # Google Calendar backend
    # ------------------------------------------------------------------ #
    async def _google_free_slots(self, day: datetime, duration_min: int) -> list[str]:
        """Use freebusy to subtract busy intervals from the business-hours grid."""
        cal_id = getattr(self, "_calendar_id", "primary")
        start = datetime.combine(day.date(), BUSINESS_START)
        end = datetime.combine(day.date(), BUSINESS_END)

        body = {
            "timeMin": start.isoformat() + "+05:30",
            "timeMax": end.isoformat() + "+05:30",
            "items": [{"id": cal_id}],
        }
        resp = await asyncio.to_thread(self._gcal.freebusy().query(body=body).execute)
        busy = resp.get("calendars", {}).get(cal_id, {}).get("busy", [])

        candidate = self._sim_free_slots(day, duration_min)
        free: list[str] = []
        for slot in candidate:
            slot_start = datetime.fromisoformat(slot)
            slot_end = slot_start + timedelta(minutes=duration_min)
            if not self._overlaps_busy(slot_start, slot_end, busy):
                free.append(slot)
        return free

    @staticmethod
    def _overlaps_busy(slot_start, slot_end, busy: list[dict[str, str]]) -> bool:
        for b in busy:
            try:
                b_start = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
                b_end = datetime.fromisoformat(b["end"].replace("Z", "+00:00"))
                # Compare naive to naive (drop tz for the simple grid check).
                b_start = b_start.replace(tzinfo=None)
                b_end = b_end.replace(tzinfo=None)
                if slot_start < b_end and slot_end > b_start:
                    return True
            except Exception:
                continue
        return False

    async def _google_book(
        self, when: datetime, name: str, phone: str, notes: str, duration_min: int
    ) -> BookingResult:
        cal_id = getattr(self, "_calendar_id", "primary")
        end = when + timedelta(minutes=duration_min)
        event = {
            "summary": f"AI Voice Agent — meeting with {name or 'lead'}",
            "description": (
                f"Booked via AI voice agent.\nLead: {name}\nPhone: {phone}\n" f"Notes: {notes}"
            ),
            "start": {"dateTime": when.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Kolkata"},
        }
        created = await asyncio.to_thread(
            self._gcal.events().insert(calendarId=cal_id, body=event).execute
        )
        event_id = created.get("id", str(uuid.uuid4()))
        booking_id = f"bk_{event_id}"
        self._bookings[booking_id] = {
            "event_id": event_id,
            "when": when.isoformat(),
            "name": name,
            "phone": phone,
            "notes": notes,
        }
        self._taken.add(when.isoformat())
        return BookingResult(
            ok=True,
            booking_id=booking_id,
            when=when.isoformat(),
            provider="google",
            confirmation_text=self._confirm_text(when, name),
            meta={"event_id": event_id, "html_link": created.get("htmlLink")},
        )

    # ------------------------------------------------------------------ #
    # In-memory simulation backend
    # ------------------------------------------------------------------ #
    def _sim_free_slots(self, day: datetime, duration_min: int) -> list[str]:
        """Generate business-hours slots for `day`, minus already-taken ones."""
        slots: list[str] = []
        cursor = datetime.combine(day.date(), BUSINESS_START)
        end = datetime.combine(day.date(), BUSINESS_END)
        step = timedelta(minutes=max(duration_min, DEFAULT_DURATION_MIN))

        # Closed on Sundays -> roll to next business day.
        if day.weekday() not in BUSINESS_DAYS:
            return self._sim_free_slots(self._next_business_day(day), duration_min)

        now = datetime.now()
        while cursor + timedelta(minutes=duration_min) <= end:
            iso = cursor.isoformat()
            # Skip past slots (if booking for today) and already-taken slots.
            if cursor > now and iso not in self._taken:
                slots.append(iso)
            cursor += step
        return slots

    def _sim_book(
        self, when: datetime, name: str, phone: str, notes: str, duration_min: int
    ) -> BookingResult:
        iso = when.isoformat()
        if iso in self._taken:
            return BookingResult(
                ok=False,
                provider="simulation",
                when=iso,
                error="Slot already booked.",
                confirmation_text=(
                    "Woh slot abhi book ho gaya — main aapko aas-paas ka dusra " "time de doon?"
                ),
            )
        booking_id = f"bk_{uuid.uuid4().hex[:12]}"
        self._bookings[booking_id] = {
            "event_id": booking_id,
            "when": iso,
            "name": name,
            "phone": phone,
            "notes": notes,
            "duration_min": duration_min,
        }
        self._taken.add(iso)
        logger.info(f"📅 [SIMULATION] Booked {booking_id} @ {iso} for {name}/{phone}")
        return BookingResult(
            ok=True,
            booking_id=booking_id,
            when=iso,
            provider="simulation",
            confirmation_text=self._confirm_text(when, name),
            meta={"duration_min": duration_min},
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _confirm_text(when: datetime, name: str) -> str:
        nice = when.strftime("%A, %d %b %Y %I:%M %p")
        who = f"{name}, " if name else ""
        return (
            f"Perfect {who}aapki meeting {nice} IST ke liye book ho gayi hai. "
            f"Aapko reminder mil jayega. Dhanyavaad!"
        )

    @staticmethod
    def _next_business_day(day: datetime) -> datetime:
        d = day
        for _ in range(7):
            d = d + timedelta(days=1)
            if d.weekday() in BUSINESS_DAYS:
                return d
        return day + timedelta(days=1)

    def _parse_date(self, date_str: str) -> datetime:
        """Parse 'YYYY-MM-DD'; invalid/empty -> next business day from today."""
        date_str = (date_str or "").strip()
        if date_str:
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            # Try ISO datetime
            try:
                return datetime.fromisoformat(date_str)
            except ValueError:
                pass
        return self._next_business_day(datetime.now())

    @staticmethod
    def _normalize_when(when_iso: str) -> datetime | None:
        """Accept ISO datetime; return None if unparseable."""
        when_iso = (when_iso or "").strip()
        if not when_iso:
            return None
        try:
            dt = datetime.fromisoformat(when_iso.replace("Z", ""))
            return dt.replace(tzinfo=None)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d-%m-%Y %H:%M"):
                try:
                    return datetime.strptime(when_iso, fmt)
                except ValueError:
                    continue
        return None

    def validate_config(self) -> dict[str, Any]:
        """Diagnostics for dashboard / health checks."""
        return {
            "active_provider": self.provider,
            "simulation_mode": self.provider == "simulation",
            "business_hours": "Mon-Sat 10:00-18:00 IST",
            "bookings_held": len(self._bookings),
            "note": (
                "Running in SIMULATION mode — set GOOGLE_CALENDAR_CREDENTIALS + "
                "GOOGLE_CALENDAR_ID to enable real Google Calendar."
                if self.provider == "simulation"
                else f"Active provider '{self.provider}'."
            ),
        }


# ---------------------------------------------------------------------- #
# Module-level singleton
# ---------------------------------------------------------------------- #
_calendar: CalendarBooking | None = None


def get_calendar() -> CalendarBooking:
    """Return the process-wide CalendarBooking singleton (lazy init)."""
    global _calendar
    if _calendar is None:
        _calendar = CalendarBooking()
    return _calendar


__all__ = ["CalendarBooking", "BookingResult", "get_calendar"]
