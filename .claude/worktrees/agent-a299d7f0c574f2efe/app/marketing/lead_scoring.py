"""
lead_scoring.py — website inquiries ka rule-based hot/warm/cold scoring.
=========================================================================

data/inquiries.jsonl (public_site.py jo likhta hai) padh kar har lead ko
0-100 score deta hai — PURE RULES, koi LLM nahi, kabhi raise nahi:

  phone valid (10-12 digits)            +20
  niche S-tier                          +20
  message len > 20                      +15
  city diya hai                         +10
  recency: <48h +25 / <7d +15 / else +5
  source == website                     +10
  ------------------------------------------
  label: hot >= 70 | warm 40-69 | cold < 40

score_leads() -> {"total","counts":{hot,warm,cold},"leads":[...score desc]}
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# public_site.py ke saath same path — tests isse monkeypatch karte hain.
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")

# S-tier niches (CLAUDE.md / niches.py research-finalized list)
_S_TIER = {
    "ai_marketing",
    "real_estate",
    "solar_residential",
    "insurance",
    "home_loans",
    "coaching",
    "studying_abroad",
    "real_estate_luxury",
}

_HOT = 70
_WARM = 40


def _read_inquiries(limit: int = 500) -> list[dict[str, Any]]:
    """jsonl ki aakhri `limit` lines (parse-safe, corrupt skip, kabhi raise nahi)."""
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_INQUIRIES_FILE):
            return out
        with open(_INQUIRIES_FILE, encoding="utf-8") as f:
            lines = f.readlines()[-max(1, limit) :]
        for ln in lines:
            try:
                rec = json.loads(ln)
                if isinstance(rec, dict):
                    out.append(rec)
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[lead_scoring] inquiries read failed: {e}")
    return out


def _digits(raw: Any) -> str:
    return "".join(c for c in str(raw or "") if c.isdigit())


def _phone_valid(raw: Any) -> bool:
    return 10 <= len(_digits(raw)) <= 12


def _wa_link(raw: Any) -> str:
    """10-digit Indian number -> wa.me link ('' agar unusable)."""
    d = _digits(raw)
    if d.startswith("91") and len(d) == 12:
        d = d[2:]
    elif d.startswith("0") and len(d) == 11:
        d = d[1:]
    if len(d) != 10:
        return ""
    msg = "Namaste! Aapki website inquiry mili — kab baat kar sakte hain?"
    return f"https://wa.me/91{d}?text={quote(msg)}"


def _age_hours(at: Any) -> float:
    """ISO timestamp ('...Z' bhi) -> ab se hours. Unparseable = bahut purana."""
    s = str(at or "").strip()
    if not s:
        return 1e9
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
    except Exception:
        return 1e9


def _score_one(rec: dict[str, Any]) -> int:
    score = 0
    if _phone_valid(rec.get("phone")):
        score += 20
    niche = str(rec.get("niche") or "").strip().lower()
    if niche in _S_TIER:
        score += 20
    if len(str(rec.get("message") or "").strip()) > 20:
        score += 15
    if str(rec.get("city") or "").strip():
        score += 10
    hours = _age_hours(rec.get("at"))
    if hours < 48:
        score += 25
    elif hours < 24 * 7:
        score += 15
    else:
        score += 5
    if str(rec.get("source") or "").strip().lower() == "website":
        score += 10
    return min(100, score)


def _label_of(score: int) -> str:
    return "hot" if score >= _HOT else ("warm" if score >= _WARM else "cold")


def score_leads() -> dict[str, Any]:
    """Saari inquiries score karke sorted list + counts lautao. Kabhi raise nahi."""
    leads: list[dict[str, Any]] = []
    counts = {"hot": 0, "warm": 0, "cold": 0}
    for rec in _read_inquiries():
        try:
            score = _score_one(rec)
            label = _label_of(score)
            counts[label] += 1
            leads.append(
                {
                    "name": str(rec.get("name") or "").strip()[:120],
                    "business_name": str(rec.get("business_name") or "").strip()[:200],
                    "phone": str(rec.get("phone") or "").strip()[:20],
                    "niche": str(rec.get("niche") or "").strip()[:50],
                    "city": str(rec.get("city") or "").strip()[:100],
                    "score": score,
                    "label": label,
                    "at": str(rec.get("at") or "")[:40],
                    "wa_link": _wa_link(rec.get("phone")),
                }
            )
        except Exception:  # pragma: no cover - _score_one defensive hai
            continue
    # score desc; same score par newest pehle (stable two-pass sort)
    leads.sort(key=lambda r: r["at"], reverse=True)
    leads.sort(key=lambda r: r["score"], reverse=True)
    return {
        "total": len(leads),
        "counts": counts,
        "leads": leads,
        "tip": "Hot leads ko 5 minute ke andar WhatsApp/call karo — response "
        "rate 8-10x hota hai. Warm ko aaj, cold ko drip me daalo.",
    }
