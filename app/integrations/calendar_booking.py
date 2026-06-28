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
import json
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

# Durable bookings ledger (gitignored data/). Every successful booking — internal,
# Google, or Cal.com — is appended here so a phone/web call's appointment SURVIVES
# a restart and the business owner can actually see/act on it (the old in-memory
# "simulation" lost everything on restart and notified no one).
DATA_BOOKINGS_DIR = os.path.join("data", "bookings")


def _booking_notify_enabled() -> bool:
    """BOOKING_NOTIFY (default ON): on a successful booking, best-effort ntfy +
    email so the business owner is told. Inert when no target is configured."""
    return (os.getenv("BOOKING_NOTIFY", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


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
                    self.provider = "internal"
            except Exception as e:
                logger.error(f"Google Calendar init failed ({e}); using internal store.")
                self.provider = "internal"

        if self.provider == "internal":
            logger.info(
                "📅 CalendarBooking in INTERNAL mode — durable bookings ledger "
                "(data/bookings/), no calendar keys needed. Slots: Mon-Sat 10:00-18:00 IST."
            )
        else:
            logger.info(f"📅 CalendarBooking active provider: {self.provider}")

        # Restore today's taken slots from the durable ledger so a restart can't
        # double-book a slot already taken earlier today. Best-effort, never raises.
        self._load_today_taken()

    # ------------------------------------------------------------------ #
    # Provider detection / construction
    # ------------------------------------------------------------------ #
    def _detect_provider(self) -> str:
        """Pick 'calcom' (BYOK API key — no OAuth), else 'google' (service-account
        creds), else 'internal' (durable local ledger, no keys needed)."""
        if _setting("CALCOM_API_KEY") and _setting("CALCOM_EVENT_TYPE_ID"):
            return "calcom"
        creds = _setting("GOOGLE_CALENDAR_CREDENTIALS") or _setting("google_sheets_credentials")
        cal_id = _setting("GOOGLE_CALENDAR_ID")
        if creds and os.path.exists(creds) and cal_id:
            return "google"
        return "internal"

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
        client_id: str = "",
        niche: str = "",
    ) -> BookingResult:
        """
        Book an appointment at `when_iso` for `name` / `phone`.

        Tries the active provider (Cal.com / Google), always falling back to the
        durable internal ledger. On success the booking is PERSISTED to
        data/bookings/ and the business owner is notified (best-effort);
        `client_id` / `niche` route that notification. Never raises — returns
        BookingResult(ok=False, error=...) on failure.
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

        result: BookingResult | None = None
        if self.provider == "calcom":
            try:
                result = await self._calcom_book(when, name, phone, notes, duration_min)
            except Exception as e:
                logger.error(f"Cal.com booking failed ({e}); using internal ledger.")
        elif self.provider == "google" and self._gcal is not None:
            try:
                result = await self._google_book(when, name, phone, notes, duration_min)
            except Exception as e:
                logger.error(f"Google booking failed ({e}); using internal ledger.")

        if result is None:
            result = self._internal_book(when, name, phone, notes, duration_min)

        # Durable record + owner notification on success (every provider).
        if result and result.ok:
            try:
                self._record_booking(
                    result,
                    name=name,
                    phone=phone,
                    notes=notes,
                    niche=niche,
                    client_id=client_id,
                    duration_min=duration_min,
                )
            except Exception as e:
                logger.debug(f"calendar: record/notify skipped ({e})")
        return result

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

    def _internal_book(
        self, when: datetime, name: str, phone: str, notes: str, duration_min: int
    ) -> BookingResult:
        """Durable internal booking (no external calendar). The record is PERSISTED
        by book_slot's _record_booking, so it survives a restart (the old in-memory
        'simulation' did not)."""
        iso = when.isoformat()
        if iso in self._taken:
            return BookingResult(
                ok=False,
                provider="internal",
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
        logger.info(f"📅 [internal] Booked {booking_id} @ {iso} for {name}/{phone}")
        return BookingResult(
            ok=True,
            booking_id=booking_id,
            when=iso,
            provider="internal",
            confirmation_text=self._confirm_text(when, name),
            meta={"duration_min": duration_min},
        )

    # ------------------------------------------------------------------ #
    # Cal.com backend (BYOK API key — NO OAuth). Optional: set CALCOM_API_KEY +
    # CALCOM_EVENT_TYPE_ID. Availability uses the internal business-hours grid;
    # only the booking is pushed to Cal.com (its availability API is heavier).
    # ------------------------------------------------------------------ #
    async def _calcom_book(
        self, when: datetime, name: str, phone: str, notes: str, duration_min: int
    ) -> BookingResult:
        api_key = _setting("CALCOM_API_KEY")
        event_type_id = _setting("CALCOM_EVENT_TYPE_ID")
        base = _setting("CALCOM_API_BASE") or "https://api.cal.com/v1"
        if not api_key or not event_type_id:
            raise RuntimeError("Cal.com creds missing")
        import httpx

        # Cal.com needs an attendee email; phone leads often lack one -> derive a
        # stable placeholder so the booking still goes through.
        email = (
            _setting("CALCOM_ATTENDEE_EMAIL")
            or f"{(phone or 'lead').strip() or 'lead'}@voice.leadsgenai.in"
        )
        payload = {
            "eventTypeId": int(event_type_id),
            "start": when.isoformat(),
            "responses": {"name": name or "Lead", "email": email},
            "timeZone": "Asia/Kolkata",
            "language": "en",
            "metadata": {"source": "ai_voice_agent", "phone": phone, "notes": notes},
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                f"{base.rstrip('/')}/bookings", params={"apiKey": api_key}, json=payload
            )
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        node = data.get("booking") if isinstance(data, dict) else None
        node = node if isinstance(node, dict) else (data if isinstance(data, dict) else {})
        ext = str(node.get("uid") or node.get("id") or uuid.uuid4().hex[:12])
        booking_id = f"calcom_{ext}"
        self._bookings[booking_id] = {
            "event_id": ext,
            "when": when.isoformat(),
            "name": name,
            "phone": phone,
            "notes": notes,
        }
        self._taken.add(when.isoformat())
        logger.info(f"📅 [calcom] Booked {booking_id} @ {when.isoformat()}")
        return BookingResult(
            ok=True,
            booking_id=booking_id,
            when=when.isoformat(),
            provider="calcom",
            confirmation_text=self._confirm_text(when, name),
            meta={"calcom_id": ext},
        )

    # ------------------------------------------------------------------ #
    # Durable ledger + owner notification (the "real booking" guarantees)
    # ------------------------------------------------------------------ #
    def _record_booking(
        self,
        result: BookingResult,
        *,
        name: str,
        phone: str,
        notes: str,
        niche: str,
        client_id: str,
        duration_min: int,
    ) -> None:
        """Persist the booking to the durable ledger + notify the owner. Best-effort."""
        rec = {
            "booking_id": result.booking_id,
            "when": result.when,
            "provider": result.provider,
            "name": name or "",
            "phone": phone or "",
            "notes": notes or "",
            "niche": niche or "",
            "client_id": str(client_id or ""),
            "duration_min": duration_min,
            "booked_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._persist_booking(rec)
        if _booking_notify_enabled():
            self._notify_owner(rec)

    @staticmethod
    def _persist_booking(rec: dict[str, Any]) -> None:
        """Append one booking to data/bookings/YYYY-MM-DD.jsonl. Never raises."""
        try:
            os.makedirs(DATA_BOOKINGS_DIR, exist_ok=True)
            day = datetime.now().strftime("%Y-%m-%d")
            path = os.path.join(DATA_BOOKINGS_DIR, day + ".jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"calendar: persist failed ({e})")

    def _notify_owner(self, rec: dict[str, Any]) -> None:
        """Best-effort ntfy push + email so the business owner is told a meeting was
        booked. Routes email to the client owner (client_id) else NOTIFY_EMAIL.
        Never raises; inert when no target is configured."""
        when = rec.get("when") or ""
        name = rec.get("name") or "lead"
        phone = rec.get("phone") or ""
        niche = rec.get("niche") or ""
        title = "📅 New appointment booked (AI voice agent)"
        msg = f"{when} — {name} {phone} ({niche})".strip()
        try:
            from app.platform.ops_alerts import _ntfy

            _ntfy(title, msg, priority="default", tags=["calendar", "spiral_calendar"])
        except Exception:
            pass
        try:
            to = self._owner_email(rec.get("client_id") or "")
            if not to:
                return
            from app.integrations.email_sender import EmailSender

            async def _send() -> None:
                try:
                    body = f"{msg}\n\nNotes: {rec.get('notes', '')}\nBooking: {rec.get('booking_id', '')}"
                    await EmailSender().send_email([to], title, body)
                except Exception:
                    pass

            try:
                asyncio.get_running_loop().create_task(_send())
            except RuntimeError:  # no running loop — fire synchronously
                asyncio.run(_send())
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"calendar: owner notify failed ({e})")

    @staticmethod
    def _owner_email(client_id: str) -> str:
        """Client owner email (if resolvable) else NOTIFY_EMAIL admin fallback."""
        cid = (client_id or "").strip()
        if cid:
            try:
                from app.marketing.clients_store import get_client

                c = get_client(cid) or {}
                for k in ("email", "owner_email", "contact_email"):
                    if c.get(k):
                        return str(c[k]).strip()
            except Exception:
                pass
        return _setting("NOTIFY_EMAIL")

    def _load_today_taken(self) -> None:
        """Restore taken slots from the ledger (restart double-book guard). Ledger files
        are keyed by BOOKED-AT date, so a slot booked days ago for a FUTURE appointment
        lives in an OLDER file — scan a recent window of booked-at files (not just today),
        else a cross-day restart re-offers an already-booked future slot."""
        try:
            today = datetime.now()
            for d in range(0, 90):  # last 90 booked-at days — covers realistic lead time
                day = (today - timedelta(days=d)).strftime("%Y-%m-%d")
                for rec in self.list_bookings(limit=0, date_str=day):
                    w = rec.get("when")
                    if w:
                        self._taken.add(w)
        except Exception:  # pragma: no cover - defensive
            pass

    @staticmethod
    def list_bookings(limit: int = 50, date_str: str | None = None) -> list[dict[str, Any]]:
        """Recent bookings from the durable ledger for a day (UTC-naive local day).
        For the admin view + restart restore. Never raises."""
        out: list[dict[str, Any]] = []
        try:
            day = (date_str or "").strip() or datetime.now().strftime("%Y-%m-%d")
            path = os.path.join(DATA_BOOKINGS_DIR, day + ".jsonl")
            if not os.path.exists(path):
                return out
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:  # pragma: no cover - defensive
            return out
        return out[-limit:] if limit else out

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
            "internal_mode": self.provider == "internal",
            "business_hours": "Mon-Sat 10:00-18:00 IST",
            "bookings_held": len(self._bookings),
            "notify": _booking_notify_enabled(),
            "note": (
                "INTERNAL durable ledger (data/bookings/) — bookings persist across "
                "restart + owner notified. Optional: CALCOM_API_KEY+CALCOM_EVENT_TYPE_ID "
                "(no OAuth) or GOOGLE_CALENDAR_CREDENTIALS+GOOGLE_CALENDAR_ID for sync."
                if self.provider == "internal"
                else f"Active provider '{self.provider}' (bookings also persisted locally)."
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
