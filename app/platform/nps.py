"""nps.py — NPS/CSAT collector (Formbricks/Fider ka free in-house lite).

Retention truth: clients khush hain ya nahi — guess nahi, MEASURE. 0-10 score:
9-10 promoter · 7-8 passive · 0-6 detractor. NPS = %promoters - %detractors.

- Public submit (rate-limited route growth.py me) — client/uske customer dono.
- Detractor (<=6) → turant alert email Sumit ko, GATED `NPS_ALERTS=1`
  (OFF = record-only, zero change). Promoter (>=9) → review-request ka
  natural candidate (response me `suggest_review: True` — review_engine reuse).
- `request_drafts()` — har active client ke liye 1-click WhatsApp survey link
  (ban-safe DRAFT, auto-send nahi).
- Store `data/nps_responses.jsonl`. Defensive — kabhi raise nahi karta.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "nps_responses.jsonl")


def _alerts_on() -> bool:
    return os.environ.get("NPS_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def classify(score: int) -> str:
    """Pure helper: promoter/passive/detractor."""
    s = max(0, min(10, int(score)))
    if s >= 9:
        return "promoter"
    if s >= 7:
        return "passive"
    return "detractor"


def compute_nps(scores: list[int]) -> dict[str, Any]:
    """Pure helper (testable): standard NPS calc."""
    if not scores:
        return {"nps": None, "total": 0, "promoters": 0, "passives": 0, "detractors": 0}
    buckets = {"promoter": 0, "passive": 0, "detractor": 0}
    for s in scores:
        buckets[classify(s)] += 1
    n = len(scores)
    nps = round(100 * (buckets["promoter"] - buckets["detractor"]) / n)
    return {
        "nps": nps,
        "total": n,
        "promoters": buckets["promoter"],
        "passives": buckets["passive"],
        "detractors": buckets["detractor"],
    }


def _append(row: dict) -> None:
    os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
    with open(_STORE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_all() -> list[dict]:
    try:
        if not os.path.exists(_STORE):
            return []
        with open(_STORE, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except Exception:
        return []


async def submit(
    score: int, comment: str = "", name: str = "", phone: str = "", client_slug: str = ""
) -> dict[str, Any]:
    """Response record + detractor alert (gated). Public route se aata hai."""
    try:
        score = max(0, min(10, int(score)))
        bucket = classify(score)
        row = {
            "ts": int(time.time()),
            "score": score,
            "bucket": bucket,
            "comment": (comment or "").strip()[:1000],
            "name": (name or "").strip()[:120],
            "phone": (phone or "").strip()[:20],
            "client_slug": (client_slug or "").strip()[:80],
        }
        _append(row)
        if bucket == "detractor" and _alerts_on():
            try:
                from app.integrations.email_sender import email_sender

                notify = os.environ.get("NOTIFY_EMAIL", "").strip()
                if notify:
                    await email_sender.send_email(
                        [notify],
                        f"🔴 NPS detractor ({score}/10) — {row['client_slug'] or row['name'] or 'anon'}",
                        f"Score: {score}/10\nKaun: {row['name']} {row['phone']} (client: {row['client_slug']})\n"
                        f"Comment: {row['comment'] or '(khali)'}\n\nJaldi call/WhatsApp karke issue solve karo — rating bachao.",
                    )
            except Exception as e:
                logger.warning(f"[nps] alert fail: {e}")
        return {"ok": True, "bucket": bucket, "suggest_review": bucket == "promoter"}
    except Exception as e:
        logger.warning(f"[nps] submit fail: {e}")
        return {"ok": False, "error": str(e)[:160]}


def stats(client_slug: str = "", days: int = 90) -> dict[str, Any]:
    """Admin: NPS + recent responses (optionally per client)."""
    try:
        cutoff = int(time.time()) - days * 86400
        rows = [r for r in _read_all() if r.get("ts", 0) >= cutoff]
        if client_slug:
            rows = [r for r in rows if r.get("client_slug") == client_slug]
        out = compute_nps([int(r.get("score", 0)) for r in rows])
        out["recent"] = rows[-15:][::-1]
        return out
    except Exception as e:
        return {"nps": None, "error": str(e)[:160]}


def request_drafts(limit: int = 20) -> list[dict]:
    """Har active client ke liye 1-click WhatsApp NPS-survey draft (ban-safe)."""
    try:
        from app.marketing import clients_store

        base = "https://leadsgenai.in"
        try:
            from app.config import settings

            base = (settings.public_base_url or base).rstrip("/")
        except Exception:
            pass
        drafts = []
        for c in (clients_store.list_clients() or [])[:limit]:
            phone = (c.get("phone") or "").strip()
            slug = c.get("slug") or ""
            msg = (
                f"Namaste {c.get('business_name', '')}! 🙏 Ek chhota sa sawaal — humari AI marketing "
                f"service ko 0-10 me kitna score denge? Reply me number bhej dijiye, ya yahan rate karein: "
                f"{base}/api/public/nps?slug={quote(slug)}"
            )
            drafts.append(
                {
                    "client": c.get("business_name"),
                    "slug": slug,
                    "wa_link": (
                        f"https://wa.me/{phone.lstrip('+')}?text={quote(msg)}" if phone else None
                    ),
                    "message": msg,
                }
            )
        return drafts
    except Exception as e:
        logger.warning(f"[nps] drafts fail: {e}")
        return []
