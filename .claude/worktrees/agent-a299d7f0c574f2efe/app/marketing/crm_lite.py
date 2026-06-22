"""
crm_lite.py — chhota customers store + birthday/anniversary wishes (free).
===========================================================================

Per-client customers list (naam/phone/birthday/anniversary/tags) jsonl me:
data/crm/{client_id}.jsonl — append-only, phone(10-digit) par dedupe.

  add_customers(client_id, rows)   -> {"added","skipped","total"}
  list_customers(client_id, tag)   -> [customer dicts] (optional tag filter)
  todays_wishes(client_id, biz)    -> aaj (IST, MM-DD) jinke birthday/
        anniversary hain unke ready Hinglish wish messages + wa.me links.

Template-based (LLM optional nahi chahiye — wishes personal/chhoti hoti hain).
Pure stdlib; read/list/wishes kabhi raise nahi karte.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CRM_DIR = os.path.join("data", "crm")
_IST = timezone(timedelta(hours=5, minutes=30))


def _safe_id(client_id: Any) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]", "_", str(client_id or "").strip())[:64]
    return s or "default"


def _path(client_id: Any) -> str:
    return os.path.join(_CRM_DIR, _safe_id(client_id) + ".jsonl")


def _digits10(raw: Any) -> str:
    """Sirf digits; +91/0 prefix normalize karke 10-digit lautao ('' = unusable)."""
    digits = "".join(c for c in str(raw or "") if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def _mmdd(value: Any) -> str:
    """Date ko 'MM-DD' me normalize karo ('1990-06-07' ya '06-07'); invalid = ''."""
    s = str(value or "").strip()
    if not s:
        return ""
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m:
        mo, d = int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", s)
        if not m:
            return ""
        mo, d = int(m.group(1)), int(m.group(2))
    if 1 <= mo <= 12 and 1 <= d <= 31:
        return f"{mo:02d}-{d:02d}"
    return ""


def _today_mmdd() -> str:
    return datetime.now(_IST).strftime("%m-%d")


def _read(client_id: Any) -> list[dict[str, Any]]:
    path = _path(client_id)
    rows: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(path):
            return rows
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict) and row.get("phone"):
                        rows.append(row)
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"[crm_lite] read failed for {path}: {e}")
    return rows


def add_customers(client_id: Any, rows: list[dict[str, Any]] | None) -> dict[str, int]:
    """Customers add karo (phone-10digit dedupe, existing + same-batch dono).

    rows: [{"name","phone","birthday"?,"anniversary"?,"tags"?}, ...]
    Returns: {"added","skipped","total"}.
    """
    existing = _read(client_id)
    seen = {r.get("phone") for r in existing}
    added, skipped = 0, 0
    new_recs: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            skipped += 1
            continue
        d10 = _digits10(row.get("phone"))
        if not d10 or d10 in seen:
            skipped += 1
            continue
        seen.add(d10)
        tags = row.get("tags") or []
        if not isinstance(tags, list):
            tags = [tags]
        new_recs.append(
            {
                "name": str(row.get("name") or "").strip()[:80] or "Customer",
                "phone": d10,
                "birthday": _mmdd(row.get("birthday")),
                "anniversary": _mmdd(row.get("anniversary")),
                "tags": [str(t).strip()[:30] for t in tags if str(t).strip()][:10],
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        added += 1
    if new_recs:
        os.makedirs(_CRM_DIR, exist_ok=True)
        with open(_path(client_id), "a", encoding="utf-8") as f:
            for rec in new_recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"added": added, "skipped": skipped, "total": len(existing) + added}


def list_customers(client_id: Any, tag: str | None = None) -> list[dict[str, Any]]:
    """Saved customers (newest last). Optional tag filter. Kabhi raise nahi."""
    rows = _read(client_id)
    t = (tag or "").strip().lower()
    if t:
        rows = [r for r in rows if t in [str(x).lower() for x in (r.get("tags") or [])]]
    return rows


_WISH_TEMPLATES = {
    "birthday": (
        "🎂 Janamdin bahut bahut mubarak ho, {name} ji! 🎉 {biz} ki "
        "poori team ki taraf se dher saari shubhkamnayein. Aapka din "
        "khushiyon se bhara rahe! 🙏"
    ),
    "anniversary": (
        "💐 Shaadi ki salgirah mubarak ho, {name} ji! {biz} ki "
        "taraf se aap dono ko dher saari badhai — aapka saath yun "
        "hi bana rahe! 🎉🙏"
    ),
}


async def todays_wishes(client_id: Any, business_name: str = "") -> dict[str, Any]:
    """Aaj (IST) ke birthday/anniversary customers ke ready wish messages.

    Returns: {"date","count","wishes":[{name,phone,occasion,message,wa_link}]}.
    Template-based — instant, deterministic, KABHI raise nahi.
    """
    biz = (business_name or "").strip() or "Hamari team"
    today = _today_mmdd()
    wishes: list[dict[str, str]] = []
    for cust in _read(client_id):
        occasions = []
        if cust.get("birthday") == today:
            occasions.append("birthday")
        if cust.get("anniversary") == today:
            occasions.append("anniversary")
        for occ in occasions:
            name = str(cust.get("name") or "").strip() or "ji"
            msg = _WISH_TEMPLATES[occ].format(name=name, biz=biz)
            d10 = _digits10(cust.get("phone"))
            wishes.append(
                {
                    "name": name,
                    "phone": d10,
                    "occasion": occ,
                    "message": msg,
                    "wa_link": f"https://wa.me/91{d10}?text={quote(msg)}" if d10 else "",
                }
            )
    return {
        "date": today,
        "business_name": biz,
        "count": len(wishes),
        "wishes": wishes,
        "tip": (
            "Wish subah 9-10 baje bhejo — personal touch ke liye apne naam "
            "se 1 line add kar lo. Ye chhoti cheez repeat business laati hai."
        ),
    }
