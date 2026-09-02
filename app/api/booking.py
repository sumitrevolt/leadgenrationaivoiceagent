"""Booking API — Calendly-lite slots + booking over the existing calendar_booking engine.

Thin, defensive REST surface over `app/integrations/calendar_booking.py` (Google Calendar
when configured, else in-memory business-hours simulation). Public-friendly: a client's
website/mini-site can list free slots and book. Never crashes (serializes whatever the
engine returns).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/booking", tags=["Booking"])


def _resolve_client_id(slug: str) -> str:
    """Mini-site slug → owning client_id so slot availability/booking is scoped PER
    business (jiya's booked slot must NOT block another studio's same slot). Cheap
    sync lookup; slug fallback still isolates mini-sites if the client isn't found
    (that fallback alone fixes the shared-singleton bug). Never raises."""
    slug = (slug or "").strip()
    if not slug:
        return ""
    try:
        from app.marketing.clients_store import get_by_slug

        c = get_by_slug(slug) or {}
        return str(c.get("id") or "").strip() or slug
    except Exception:
        return slug


def _ser(obj: Any) -> Any:
    """Best-effort serialize a slot / BookingResult (dataclass / .as_dict / dict / str)."""
    try:
        if obj is None or isinstance(obj, (str, int, float, bool, dict)):
            return obj
        for meth in ("as_dict", "to_dict", "dict"):
            fn = getattr(obj, meth, None)
            if callable(fn):
                return fn()
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
        return str(obj)
    except Exception:
        return str(obj)


@router.get("/slots", dependencies=[Depends(rate_limit("booking_slots", 30, 60))])
async def get_slots(
    date: str = Query("", max_length=10),
    duration_min: int = Query(15, ge=5, le=120),
    slug: str = Query("", max_length=80),
):
    """Free appointment slots for a date (YYYY-MM-DD; empty = next working day).

    `slug` scopes availability to the mini-site's owning business — a slot taken by
    ANOTHER client (or the global/legacy pool) does not hide it here."""
    try:
        from app.integrations.calendar_booking import get_calendar

        cal = get_calendar()
        slots = await cal.check_availability(
            date or None, duration_min=duration_min, client_id=_resolve_client_id(slug)
        )
        return {"date": date, "slots": [_ser(s) for s in (slots or [])]}
    except Exception as e:
        logger.error(f"booking slots failed: {e}")
        raise HTTPException(status_code=503, detail="Slots abhi available nahi — baad me try karo.")


class BookIn(BaseModel):
    slot: Any  # the slot object/dict returned by /slots (passed back as-is)
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=6, max_length=20)
    notes: str = Field("", max_length=400)
    slug: str = Field("", max_length=80)  # mini-site slug → scope booking per business


@router.post("/book", dependencies=[Depends(rate_limit("booking_book", 10, 60))])
async def book_slot(req: BookIn):
    """Book a slot returned by /slots. Returns the booking confirmation.

    `slug` scopes the double-book guard PER business — two different clients can hold
    the same wall-clock slot; the same client can't double-book it."""
    try:
        from app.integrations.calendar_booking import get_calendar

        cal = get_calendar()
        client_id = _resolve_client_id(req.slug)
        res = await cal.book_slot(
            req.slot, name=req.name, phone=req.phone, notes=req.notes, client_id=client_id
        )
        # Persistent record + reminder pipeline (best-effort — booking kabhi na ruke)
        try:
            from app.platform import booking_reminders

            slot_iso = ""
            try:
                slot_iso = (
                    req.slot.get("iso") or req.slot.get("start") or str(req.slot)
                    if isinstance(req.slot, dict)
                    else str(req.slot)
                )
            except Exception:
                slot_iso = str(req.slot)
            booking_reminders.record_booking(slot_iso, req.name, req.phone, notes=req.notes)
        except Exception as e:
            logger.debug(f"[booking] reminder record skip: {e}")
        # Outbound webhook (Zapier-style, inert bina registered hooks)
        try:
            import asyncio as _aio

            from app.platform import outbound_webhooks

            _aio.get_event_loop().create_task(
                outbound_webhooks.emit(
                    "booking",
                    {"name": req.name, "phone": req.phone[-10:], "slot": str(req.slot)[:60]},
                )
            )
        except Exception:
            pass
        return _ser(res)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"booking book failed: {e}")
        raise HTTPException(
            status_code=503, detail="Booking abhi possible nahi — baad me try karo."
        )


class CancelIn(BaseModel):
    booking_id: str = Field(..., min_length=1, max_length=80)
    # Possession factor — must match the phone the booking was made with. Stops a
    # leaked/guessed booking_id alone from cancelling someone else's appointment.
    phone: str = Field(..., min_length=6, max_length=20)


@router.post("/cancel", dependencies=[Depends(rate_limit("booking_cancel", 10, 60))])
async def cancel_booking(req: CancelIn):
    try:
        from app.integrations.calendar_booking import get_calendar

        cal = get_calendar()
        # Mismatch => cancel() returns False (same shape as not-found — no oracle
        # revealing whether the booking_id exists).
        ok = await cal.cancel(req.booking_id, phone=req.phone)
        return {"ok": bool(ok), "booking_id": req.booking_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"booking cancel failed: {e}")
        raise HTTPException(status_code=503, detail="Cancel abhi possible nahi — baad me try karo.")
