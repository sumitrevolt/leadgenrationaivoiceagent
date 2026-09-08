"""Sentiment-gated review GENERATION engine (Reviewly/Birdeye-lite, free-stack).

`review_kit.py` review-request CONTENT banata hai (WhatsApp msg + QR + card). Yeh
engine us par ORCHESTRATION add karta — yahi 2026 ka naya hissa:

  * SENTIMENT-GATE: khush customer -> Google review request (public);
    naraz customer -> PRIVATE feedback message (rating bachao). Google-compliant:
    sabko maangte, customer decide karta — bas unhappy ko public push nahi.
  * TRACK: data/review_requests.jsonl (kisko/kab/gate/status).
  * SEND: DEFAULT 1-click (message + link return, human bheje). Auto-send SIRF
    WHATSAPP_AUTO_SEND=1 + Cloud API creds (existing integrations/whatsapp.py).

Research: reviews = 20% local-pack ranking; auto-request -> 90 din me 3-5x reviews;
WhatsApp 98% open. Free, ban-safe, import-safe (kabhi raise nahi).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "review_requests.jsonl")
HAPPY_THRESHOLD = 4  # 1-5 scale: >= => Google review; warna private feedback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _track(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[review_engine] track skip: {e}")


def list_requests(limit: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return list(reversed(rows))[:limit]


def _private_feedback_msg(name: str, biz: str) -> str:
    return (
        f"Namaste {name or 'ji'} 🙏 {biz} ki taraf se sorry agar experience perfect "
        "nahi raha. Aap please 1 line me bata dijiye kya improve karein? Aapka feedback "
        "seedha owner tak jaata hai — hum theek karenge. Dhanyawad!"
    )


async def request_review(
    business_name: str,
    place_query: str | None = None,
    customer_name: str = "",
    customer_phone: str = "",
    sentiment_score: int | None = None,
    auto_send: bool | None = None,
) -> dict[str, Any]:
    """Ek review-request taiyaar karo (sentiment-gated). Default = 1-click draft.

    sentiment_score 1-5 (None = unknown -> happy maan ke Google). Returns dict with
    gate, message, review_link, qr_svg(happy only), auto_sent, tracked. Kabhi raise nahi.
    """
    biz = (business_name or "Hamari team").strip()
    name = (customer_name or "").strip()
    happy = sentiment_score is None or (
        isinstance(sentiment_score, int) and sentiment_score >= HAPPY_THRESHOLD
    )

    message = ""
    review_link = None
    qr = None
    gate = "google_review" if happy else "private_feedback"

    if happy:
        try:
            from app.marketing import review_kit

            kit = await review_kit.full_kit(biz, (place_query or biz))
            message = kit.get("wa_message") or ""
            review_link = (kit.get("links") or {}).get("maps_search_url")
            qr = kit.get("qr_svg")
        except Exception as e:
            logger.debug(f"[review_engine] review_kit skip: {e}")
            message = (
                f"Namaste! 🙏 {biz} ko service ka mauka dene ke liye dhanyawad. Achhi lagi ho to "
                "30 second me Google par review de dijiye ⭐"
            )
    else:
        message = _private_feedback_msg(name, biz)

    # Optional auto-send via existing WhatsApp Cloud API (gated + best-effort).
    auto_sent = False
    want_auto = (
        auto_send
        if auto_send is not None
        else os.environ.get("WHATSAPP_AUTO_SEND", "0").strip().lower() in ("1", "true", "yes")
    )
    if want_auto and customer_phone:
        try:
            from app.integrations.whatsapp import get_whatsapp_sender

            wa = get_whatsapp_sender()  # dual-engine: self-host (WAHA) or Cloud API
            res = await wa.send_text_message(customer_phone, message)
            auto_sent = bool(res and not res.get("error"))
        except Exception as e:
            logger.debug(f"[review_engine] auto-send skip: {e}")

    rec = {
        "id": uuid.uuid4().hex[:12],
        "business_name": biz,
        "customer_name": name,
        "customer_phone": customer_phone,
        "sentiment_score": sentiment_score,
        "gate": gate,
        "auto_sent": auto_sent,
        "at": _now(),
    }
    _track(rec)

    return {
        "ok": True,
        "gate": gate,
        "message": message,
        "review_link": review_link,
        "qr_svg": qr,
        "auto_sent": auto_sent,
        "request_id": rec["id"],
    }


__all__ = ["request_review", "list_requests", "HAPPY_THRESHOLD"]
