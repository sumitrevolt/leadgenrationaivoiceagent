"""sales_qualify.py — BANT qualification, Indian local-SMB adapted.

ai-sales-team-claude (zubair-trabzada) ke BANT+MEDDIC rubric se inspired —
unka US-B2B-SaaS version funding-rounds/G2/LinkedIn pe chalta tha; humara
LOCAL SMB (solar/gym/salon) version GBP-signals pe: rating, reviews, website,
owner-access, inquiry recency. Pure-Python (no LLM/no network) = fast + testable.

Dimensions (0-25 each, total 0-100):
- Budget: dhandha chal raha hai? (rating+reviews = busy, website = invest karta)
- Authority: owner-operator = decision-maker DIRECT milta (local SMB ka edge)
- Need: marketing gap = HUMARA pitch (website nahi / reviews kam / rating low)
- Timeline: abhi garam hai? (status, recency, inquiry source)

`bant_score(prospect_dict)` → {total, grade A-D, dimension scores, reasons[],
action (Hinglish next step)}. Kabhi raise nahi karta.
NOTE: yeh EXISTING lead_scoring (priority-ranking) ka REPLACEMENT nahi —
woh "kis pe pehle dhyan do" batata, yeh "deal kitni qualified + kaise close
karein" batata (sales_team deep-dive ka hissa).
"""

from __future__ import annotations

import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

GRADES = [(75, "A"), (55, "B"), (35, "C"), (0, "D")]

_ACTIONS = {
    "A": "Aaj hi call/WhatsApp karo — full pitch + demo link bhejo (yeh closed hone layak hai).",
    "B": "Personalized outreach bhejo + 2 din me follow-up — ek strong proof point ke saath.",
    "C": "Nurture me daalo (cadence) — free audit/value content se garam karo, pitch abhi nahi.",
    "D": "Token mat jalao — low-priority list, sirf seasonal/festival touch.",
}


def _num(v: Any, default: float = 0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def score_budget(p: dict) -> tuple[int, list[str]]:
    s, why = 0, []
    rating = _num(p.get("rating"))
    reviews = int(_num(p.get("reviews") or p.get("reviews_count") or p.get("user_ratings_total")))
    if rating >= 4.2 and reviews >= 50:
        s += 9
        why.append(f"busy business ({rating}★, {reviews} reviews) = paying capacity")
    elif reviews >= 10:
        s += 5
        why.append(f"established ({reviews} reviews)")
    if (p.get("website") or "").strip():
        s += 6
        why.append("website hai = marketing pe kharch karta hai")
    if (p.get("email") or "").strip():
        s += 3
    tier = (p.get("tier") or p.get("niche_tier") or "").upper()
    if tier == "S":
        s += 5
        why.append("S-tier niche (high ticket-size)")
    elif tier == "A":
        s += 3
    return min(s, 25), why


def score_authority(p: dict) -> tuple[int, list[str]]:
    s, why = 12, ["local SMB = owner khud decision-maker (direct access)"]
    if (p.get("phone") or "").strip():
        s += 6
        why.append("direct phone available")
    if (p.get("contact_name") or p.get("owner") or p.get("name") or "").strip():
        s += 4
    if (p.get("email") or "").strip():
        s += 3
    return min(s, 25), why


def score_need(p: dict) -> tuple[int, list[str]]:
    s, why = 0, []
    if not (p.get("website") or "").strip():
        s += 8
        why.append("website NAHI = digital gap (humara core pitch)")
    reviews = int(_num(p.get("reviews") or p.get("reviews_count") or p.get("user_ratings_total")))
    if reviews < 10:
        s += 6
        why.append("reviews <10 = Google presence weak (GBP audit pitch)")
    rating = _num(p.get("rating"), 5)
    if 0 < rating < 4.0:
        s += 5
        why.append(f"rating {rating}★ = reputation pain (review-engine pitch)")
    status = (p.get("status") or "").lower()
    if status in ("interested", "hot", "callback"):
        s += 6
        why.append(f"status '{status}' = need khud bola hai")
    return min(s, 25), why


def score_timeline(p: dict) -> tuple[int, list[str]]:
    s, why = 0, []
    status = (p.get("status") or "").lower()
    if status in ("hot", "interested"):
        s += 10
        why.append("abhi garam — turant move karo")
    elif status in ("contacted", "callback"):
        s += 5
    ts = _num(p.get("ts") or p.get("updated_at_ts") or p.get("created_ts"))
    if ts:
        age_d = (time.time() - ts) / 86400
        if age_d <= 7:
            s += 8
            why.append("last activity <7 din")
        elif age_d <= 30:
            s += 4
    src = (p.get("source") or "").lower()
    if src in ("inquiry", "widget", "audit", "missed_call", "nps"):
        s += 7
        why.append(f"inbound source ({src}) = self-qualified")
    return min(s, 25), why


def grade_of(total: int) -> str:
    for cut, g in GRADES:
        if total >= cut:
            return g
    return "D"


def bant_score(p: dict) -> dict[str, Any]:
    """Full BANT — pure, never-raise."""
    try:
        b, bw = score_budget(p or {})
        a, aw = score_authority(p or {})
        n, nw = score_need(p or {})
        t, tw = score_timeline(p or {})
        total = b + a + n + t
        g = grade_of(total)
        return {
            "total": total,
            "grade": g,
            "budget": b,
            "authority": a,
            "need": n,
            "timeline": t,
            "reasons": (bw + aw + nw + tw)[:8],
            "action": _ACTIONS[g],
        }
    except Exception as e:  # pragma: no cover
        logger.warning(f"[qualify] fail: {e}")
        return {
            "total": 0,
            "grade": "D",
            "budget": 0,
            "authority": 0,
            "need": 0,
            "timeline": 0,
            "reasons": [],
            "action": _ACTIONS["D"],
            "error": str(e)[:120],
        }
