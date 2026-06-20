"""Booking reminders (Calendly/HighLevel-pattern) — no-show kam karo.

Booking hote hi yahan persistent record hota (calendar_booking in-memory hai —
restart pe gum). Daily sweep: kal ki bookings → reminder email/WA-link draft;
auto-email **gated `BOOKING_REMINDERS=1`** (off = draft record-only).

Store: data/bookings.jsonl + booking_reminder_runs.jsonl. Reuse: email_sender.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "bookings.jsonl")
_RUNS = os.path.join("data", "booking_reminder_runs.jsonl")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    return os.environ.get("BOOKING_REMINDERS", "0").strip().lower() in ("1", "true", "yes")


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def record_booking(
    slot_iso: str, name: str = "", phone: str = "", email: str = "", notes: str = "", slug: str = ""
) -> dict[str, Any]:
    """Booking API hook — persistent record (dedupe by slot+phone). Kabhi raise nahi."""
    try:
        key_phone = "".join(c for c in str(phone or "") if c.isdigit())[-10:]
        rows = _read(_STORE)
        for r in rows:
            if r.get("slot") == slot_iso and r.get("phone") == key_phone:
                return r
        rec = {
            "id": uuid.uuid4().hex[:10],
            "slot": str(slot_iso or ""),
            "name": (name or "")[:80],
            "phone": key_phone,
            "email": (email or "").strip().lower()[:120],
            "notes": (notes or "")[:200],
            "slug": (slug or "")[:60],
            "reminded": False,
            "created_at": _now().isoformat(),
        }
        _append(_STORE, rec)
        return rec
    except Exception as e:
        logger.debug(f"[booking_reminders] record skip: {e}")
        return {"error": str(e)}


def build_reminder(rec: dict[str, Any]) -> dict[str, str]:
    """Hinglish reminder (pure fn — testable)."""
    nm = rec.get("name") or "ji"
    slot = str(rec.get("slot", ""))[:16].replace("T", " ")
    body = (
        f"Namaste {nm}!\n\nReminder: aapki appointment {slot} pe booked hai. "
        f"Time se 5 min pehle ready rahiye.\n\nReschedule karna ho to is email ka reply karo.\n"
    )
    wa = f"Namaste {nm}! Reminder: aapki appointment {slot} pe hai. Confirm karne ke liye 👍 bhejo."
    return {"subject": f"⏰ Kal ki appointment ka reminder — {slot}", "body": body, "wa_text": wa}


async def run_due() -> dict[str, Any]:
    """Daily: agle 24h ki un-reminded bookings → reminder. GATED (off = no-op)."""
    if not _enabled():
        return {"enabled": False}
    sent = 0
    try:
        rows = _read(_STORE)
        changed = False
        window_end = _now() + timedelta(hours=26)
        for rec in rows:
            try:
                if rec.get("reminded"):
                    continue
                slot = datetime.fromisoformat(str(rec.get("slot")).replace("Z", "+00:00"))
                if slot.tzinfo is None:
                    slot = slot.replace(tzinfo=timezone.utc)
                if not (_now() < slot <= window_end):
                    continue
                msg = build_reminder(rec)
                ok = False
                if rec.get("email"):
                    try:
                        from app.integrations.email_sender import email_sender

                        ok = bool(
                            await email_sender.send_email(
                                [rec["email"]], msg["subject"], msg["body"]
                            )
                        )
                    except Exception:
                        ok = False
                _append(
                    _RUNS,
                    {"booking_id": rec.get("id"), "auto_sent": ok, **msg, "at": _now().isoformat()},
                )
                rec["reminded"] = True
                sent += 1
                changed = True
            except Exception:
                continue
        if changed:
            try:
                # Lock + atomic — web (booking hook) + celery (run_due) dono likhte.
                from app.utils.file_lock import locked_rewrite

                locked_rewrite(
                    _STORE,
                    "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows),
                )
            except Exception:
                pass
        return {"enabled": True, "reminders": sent}
    except Exception as e:
        logger.warning(f"[booking_reminders] run_due failed: {e}")
        return {"enabled": True, "error": str(e)}


def upcoming(limit: int = 20) -> list[dict[str, Any]]:
    rows = [r for r in _read(_STORE) if not r.get("reminded")]
    return rows[-limit:]


def list_all(limit: int = 50) -> list[dict[str, Any]]:
    """Admin calendar — saari active bookings (no-show excluded)."""
    rows = [r for r in _read(_STORE) if not r.get("no_show")]
    return rows[-limit:]


async def mark_no_show(booking_id: str) -> dict[str, Any]:
    """Past appointment ko no-show mark karo + journey trigger (gated JOURNEY_ENGINE)."""
    if not booking_id:
        return {"ok": False, "error": "booking_id required"}
    try:
        rows = _read(_STORE)
        rec: dict[str, Any] | None = None
        for r in rows:
            if r.get("id") == booking_id:
                rec = r
                r["no_show"] = True
                r["no_show_at"] = _now().isoformat()
                break
        if not rec:
            return {"ok": False, "error": "booking not found"}
        try:
            from app.utils.file_lock import locked_rewrite

            locked_rewrite(
                _STORE,
                "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows),
            )
        except Exception:
            pass
        journey_runs = 0
        try:
            from app.marketing import journeys

            runs = await journeys.emit_event(
                "no_show",
                {
                    "name": rec.get("name") or "",
                    "phone": rec.get("phone") or "",
                    "business_name": rec.get("slug") or rec.get("name") or "",
                    "booking_id": booking_id,
                    "slot": rec.get("slot") or "",
                },
            )
            journey_runs = len(runs or [])
        except Exception as e:
            logger.debug(f"[booking_reminders] no_show journey skip: {e}")
        return {"ok": True, "booking_id": booking_id, "journey_runs": journey_runs}
    except Exception as e:
        logger.warning(f"[booking_reminders] mark_no_show failed: {e}")
        return {"ok": False, "error": str(e)[:200]}
