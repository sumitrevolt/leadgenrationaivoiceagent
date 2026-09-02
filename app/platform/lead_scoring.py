"""AI-ish lead scoring + hot-lead engine (agentic-2026 trend, free-stack).

Har lead ko 0-100 score deta weighted signals se (status, source, verification,
engagement/recency, niche-fit, qualification). Lead model me `lead_score` +
`is_hot_lead` columns PEHLE se hain (koi migration nahi) — yeh engine unhe FILL
karta + hot leads surface karta taaki outreach in-market prospects pe focus kare.

Pure-Python (koi paid API nahi). `score_lead` ek dict/Lead pe chalta. DB rescore
best-effort (session fail -> []). Import-safe, kabhi raise nahi karta.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

import os as _os

# >= isse hot lead. Default 60 (env LEAD_HOT_THRESHOLD se override).
# 2026-06-13 audit: fresh-scraped cold leads ka max score ~68 (engagement/
# qualification points sirf call/reply ke BAAD bharte). 70 threshold reachable
# hi nahi tha -> 564 leads, 0 hot -> sales-deepdive/priority-outreach flow IDLE.
# 60 = avg 37.8 se kaafi upar, top phone+email+verified cold leads ko surface
# karta taaki prioritization chale. Engagement ke baad score aur upar jaata hai.
try:
    HOT_THRESHOLD = int(_os.environ.get("LEAD_HOT_THRESHOLD", "60"))
except Exception:
    HOT_THRESHOLD = 60

# Signal weights (total cap 100). Tuning ke liye yahan badlo.
_STATUS_PTS = {
    "appointment": 40,
    "qualified": 34,
    "callback": 24,
    "contacted": 14,
    "new": 8,
    "converted": 30,  # already client-ish, still warm for upsell
    "not_interested": 0,
    "wrong_number": 0,
    "dnd": 0,
    "lost": 0,
    "rejected": 0,
}
_SOURCE_PTS = {
    "referral": 18,
    "website": 16,
    "google_maps": 10,
    "justdial": 9,
    "indiamart": 9,
    "linkedin": 8,
    "manual": 6,
    "import": 4,
}


def _as_str(v: Any) -> str:
    """Enum/str/None -> lowercase str (LeadStatus.NEW -> 'new')."""
    if v is None:
        return ""
    s = getattr(v, "value", None)
    if s is None:
        s = str(v)
    return str(s).split(".")[-1].strip().lower()


def _recency_pts(created: Any, last_called: Any) -> int:
    """Naya + recently-engaged lead = warm. Stale = thanda."""
    now = datetime.now(timezone.utc)

    def _age_days(x: Any) -> float | None:
        if not x:
            return None
        try:
            if isinstance(x, str):
                x = datetime.fromisoformat(x.replace("Z", "+00:00"))
            if x.tzinfo is None:
                x = x.replace(tzinfo=timezone.utc)
            return (now - x).total_seconds() / 86400.0
        except Exception:
            return None

    pts = 0
    age = _age_days(created)
    if age is not None:
        if age <= 2:
            pts += 12
        elif age <= 7:
            pts += 8
        elif age <= 30:
            pts += 4
    # engaged recently (called) = + ; bahut purana last-call = neutral
    lc = _age_days(last_called)
    if lc is not None and lc <= 3:
        pts += 6
    return pts


def score_components(lead: dict[str, Any]) -> dict[str, int]:
    """Score ka breakdown (transparency/debug ke liye)."""
    status = _as_str(lead.get("status"))
    source = _as_str(lead.get("source"))
    comp = {
        "status": _STATUS_PTS.get(status, 4),  # unknown status = weak signal, below "new"(8)
        "source": _SOURCE_PTS.get(source, 6),
        "verification": (
            (8 if lead.get("phone_verified") else 0)
            + (5 if lead.get("email_verified") else 0)
            + (3 if lead.get("email") else 0)
        ),
        "recency": _recency_pts(lead.get("created_at"), lead.get("last_called_at")),
        "qualification": 12 if lead.get("qualification_data") else 0,
        "niche_fit": 6 if (lead.get("niche") and _as_str(lead.get("niche")) != "general") else 0,
    }
    # engagement: thode call-attempts = engaged; bahut zyada (no pickup) = fatigue
    try:
        ca = int(lead.get("call_attempts") or 0)
    except Exception:
        ca = 0
    comp["engagement"] = 6 if 1 <= ca <= 3 else (2 if ca == 0 else 0)
    return comp


def score_lead(lead: dict[str, Any]) -> int:
    """Ek lead (dict ya Lead.to_dict()) ka 0-100 score. Kabhi raise nahi."""
    try:
        total = sum(score_components(lead).values())
        return max(0, min(100, int(total)))
    except Exception as e:
        logger.debug(f"[lead_scoring] score fail: {e}")
        return 0


def is_hot(score: int) -> bool:
    return score >= HOT_THRESHOLD


def rank(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Leads ko score + is_hot ke saath sorted (desc) lautao."""
    out = []
    for ld in leads or []:
        s = score_lead(ld)
        out.append({**ld, "lead_score": s, "is_hot_lead": is_hot(s)})
    out.sort(key=lambda x: x.get("lead_score", 0), reverse=True)
    return out


async def rescore_db(limit: int = 500) -> dict[str, Any]:
    """DB leads ko rescore karke lead_score + is_hot_lead UPDATE karo (best-effort).

    Session/DB na ho to {'ok': False}. Kabhi raise nahi karta.
    """
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.lead import Lead
    except Exception as e:
        logger.debug(f"[lead_scoring] db imports unavailable: {e}")
        return {"ok": False, "reason": "db unavailable"}
    updated = 0
    hot = 0
    try:
        async with get_async_session() as session:  # type: ignore
            res = await session.execute(select(Lead).limit(limit))
            for lead in res.scalars().all():
                try:
                    d = lead.to_dict() if hasattr(lead, "to_dict") else {}
                except Exception:
                    d = {}
                s = score_lead(d)
                lead.lead_score = s
                lead.is_hot_lead = is_hot(s)
                updated += 1
                if is_hot(s):
                    hot += 1
            await session.commit()
        # Outbound webhook: lead_hot — ek baar rescore ke baad naye hot leads ke liye.
        if hot > 0:
            try:
                import asyncio as _aio_ls

                from app.platform import outbound_webhooks as _ow_ls

                _aio_ls.create_task(
                    _ow_ls.emit(
                        "lead_hot",
                        {"hot_count": hot, "updated": updated, "threshold": HOT_THRESHOLD},
                    )
                )
            except Exception:
                pass
        return {"ok": True, "updated": updated, "hot": hot, "threshold": HOT_THRESHOLD}
    except Exception as e:
        logger.warning(f"[lead_scoring] rescore_db failed: {e}")
        return {"ok": False, "reason": str(e)[:200]}


# Hard ceiling on how many rows a single top_hot_leads() call will live-score —
# not a "first N leads" window (2026-07-04 audit: the old `.limit(2000)` had NO
# ordering, so it silently only ever considered the first ~2000 rows by DB/PK
# order, permanently excluding thousands of newer leads from "hot" ranking).
# 20000 covers today's ~5.5k leads with room to grow; raise if the DB does.
_SCAN_CAP = 20000


def _phone_key(d: dict[str, Any]) -> str:
    import re

    digits = re.sub(r"\D", "", str(d.get("phone") or ""))
    return digits[-10:] if len(digits) >= 10 else ""


async def top_hot_leads(limit: int = 25) -> dict[str, Any]:
    """DB leads ko live-score karke top (hottest) lautao (read-only, best-effort).

    Dedupes by phone (last-10-digit normalized) before ranking — separate
    ingestion paths store the same Indian number in different raw formats
    (with/without +91), so the SAME business can otherwise appear twice in a
    "who to call next" list (2026-07-04 dialer-sprint audit). Keeps whichever
    duplicate has the higher live score.
    """
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.lead import Lead
    except Exception as e:
        logger.debug(f"[lead_scoring] db imports unavailable: {e}")
        return {"ok": False, "reason": "db unavailable", "leads": []}
    try:
        async with get_async_session() as session:  # type: ignore
            res = await session.execute(select(Lead).limit(_SCAN_CAP))
            dicts = []
            for lead in res.scalars().all():
                try:
                    dicts.append(lead.to_dict() if hasattr(lead, "to_dict") else {})
                except Exception:
                    pass
            ranked = rank(dicts)
            deduped: list[dict[str, Any]] = []
            seen_phones: set[str] = set()
            for x in ranked:
                key = _phone_key(x)
                if key and key in seen_phones:
                    continue
                if key:
                    seen_phones.add(key)
                deduped.append(x)
            hot = [x for x in deduped if x.get("is_hot_lead")]
            return {
                "ok": True,
                "count": len(dicts),
                "unique_count": len(deduped),
                "hot_count": len(hot),
                "threshold": HOT_THRESHOLD,
                "leads": deduped[: max(1, min(int(limit), 100))],
            }
    except Exception as e:
        logger.warning(f"[lead_scoring] top_hot_leads failed: {e}")
        return {"ok": False, "reason": str(e)[:200], "leads": []}
    return {"ok": False, "reason": "no session", "leads": []}


__all__ = [
    "HOT_THRESHOLD",
    "score_lead",
    "score_components",
    "is_hot",
    "rank",
    "rescore_db",
    "top_hot_leads",
]
