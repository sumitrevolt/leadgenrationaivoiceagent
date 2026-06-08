"""Festival marketing calendar — India ke major tyohaar auto-schedule (AdBanao/Predis-style).

`content_schedule` ke saath kaam karta hai: ek call me upcoming festivals ko queue karo,
daily sweep (`content_schedule.run_due`) un dino content auto-PREPARE karta hai. Business
owner ko har tyohaar yaad rakhna nahi padta — Diwali/Holi/Rakhi/Independence Day sab
auto-ready. Fully FREE (sirf LLM content). Never raises.

NOTE on dates: lunar festivals har saal shift hote (±1 din) — yeh table mid-2026 me verified
(timeanddate/drikpanchang). Fixed-date national festivals (15 Aug, 2 Oct, 25 Dec, 26 Jan)
exact. Ambiguous/multi-tradition dates (Janmashtami, Karva Chauth) jaan-bujhke omit
(galat date dikhane se behtar). Indicative reminders — local panchang se confirm karo.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

# (date YYYY-MM-DD, name, emoji, content-vibe) — curated 2026 H2 + 2027 H1.
_FESTIVALS: list[tuple[str, str, str, str]] = [
    ("2026-08-15", "Independence Day", "🇮🇳", "desh-bhakti, tricolour theme, freedom offer"),
    ("2026-08-26", "Eid Milad-un-Nabi", "🌙", "barkat, community greeting"),
    ("2026-08-27", "Raksha Bandhan", "🪢", "bhai-behen pyaar, rakhi gifting, combos"),
    ("2026-09-14", "Ganesh Chaturthi", "🐘", "Bappa welcome, prosperity, eco-friendly"),
    ("2026-10-02", "Gandhi Jayanti", "🕊️", "shanti, swachhta, simplicity"),
    ("2026-10-11", "Navratri", "🪔", "9 raat, garba/dandiya, fasting-friendly menu"),
    ("2026-10-20", "Dussehra", "🏹", "buraai pe acchai, naye shuruaat, muhurat"),
    ("2026-11-06", "Dhanteras", "🪙", "kharidari shubh, gold/utensils, booking"),
    ("2026-11-08", "Diwali", "🎆", "roshni, sabse bada sale, gifting, lakshmi"),
    ("2026-11-10", "Bhai Dooj", "❤️", "bhai-behen bond, gifting"),
    ("2026-11-15", "Chhath Puja", "🌅", "surya aastha (Bihar/UP/Jharkhand)"),
    ("2026-11-24", "Guru Nanak Jayanti", "🙏", "Gurpurab, seva, langar bhaav"),
    ("2026-12-25", "Christmas", "🎄", "festive cheer, year-end sale, gifting"),
    ("2027-01-01", "New Year", "🎉", "naya saal, resolutions, fresh-start offer"),
    ("2027-01-14", "Makar Sankranti / Pongal", "🪁", "patang, til-gud, harvest, surya"),
    ("2027-01-26", "Republic Day", "🇮🇳", "desh-bhakti, republic-day offer"),
    ("2027-03-05", "Maha Shivratri", "🔱", "Shiv bhakti, vrat, raat jagran"),
    ("2027-03-22", "Holi", "🌈", "rang, masti, spring sale, gujiya/thandai"),
    ("2027-04-08", "Ugadi / Gudi Padwa", "🌿", "naya saal (South/West), new beginnings"),
    ("2027-04-14", "Ram Navami / Baisakhi", "🚩", "Ram Navami bhakti + Baisakhi harvest"),
]


def _today() -> date:
    return date.today()


def upcoming(months_ahead: int = 6, limit: int = 30) -> list[dict[str, Any]]:
    """Aaj se `months_ahead` tak ke festivals (date-sorted, days_away ke saath)."""
    out: list[dict[str, Any]] = []
    try:
        today = _today()
        horizon = max(1, months_ahead) * 31
        for d_iso, name, emoji, vibe in _FESTIVALS:
            try:
                d = datetime.strptime(d_iso, "%Y-%m-%d").date()
            except Exception:
                continue
            days = (d - today).days
            if 0 <= days <= horizon:
                out.append(
                    {"date": d_iso, "name": name, "emoji": emoji, "vibe": vibe, "days_away": days}
                )
        out.sort(key=lambda x: x["date"])
    except Exception as e:
        logger.info("festival upcoming err: %s", e)
    return out[:limit]


def autoschedule(
    business_name: str,
    niche: str = "general",
    months_ahead: int = 3,
    client_id: str = "",
) -> dict[str, Any]:
    """Upcoming festivals ko content_schedule me queue karo (dup-safe). Returns count+items."""
    res: dict[str, Any] = {"scheduled": 0, "skipped": 0, "items": []}
    try:
        from app.marketing import content_schedule

        bn = (business_name or "").strip() or "Aapka Business"
        fests = upcoming(months_ahead=months_ahead)
        existing = {
            (i.get("business_name"), i.get("date"), i.get("occasion"))
            for i in content_schedule.list_scheduled()
        }
        for f in fests:
            occasion = f["name"]
            if (bn, f["date"], occasion) in existing:
                res["skipped"] += 1
                continue  # already queued — duplicate na ho
            item = content_schedule.schedule(
                business_name=bn,
                niche=niche,
                date_iso=f["date"],
                occasion=occasion,
                offer="",
                channel="instagram",
                client_id=client_id,
            )
            res["items"].append({"date": f["date"], "name": f["name"], "id": item.get("id")})
            res["scheduled"] += 1
        try:
            from app.platform.team import log_event

            log_event("isha", "festival_autoschedule", f"{res['scheduled']} festivals queued for {bn}")
        except Exception:
            pass
    except Exception as e:
        logger.info("festival autoschedule err: %s", e)
    return res


__all__ = ["upcoming", "autoschedule"]
