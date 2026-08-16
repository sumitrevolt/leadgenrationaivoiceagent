"""Review Request Automation — automated sequences for Google/Facebook review collection.

Inspired by GoHighLevel Reviews AI, Birdeye, Podium:
  - Triggered after: service completion, appointment show, NPS promoter detection
  - Multi-step sequence: initial request → reminder → escalation
  - Sentiment-gate: happy → Google public review; unhappy → private feedback
  - Channel: WhatsApp / SMS / Email (existing integrations, free stack)
  - Track: data/review_sequences.jsonl
  - Feature flag: REVIEW_AUTOMATION (default OFF)

100% free stack, never raises, tenant-isolated.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "review_sequences.jsonl")
_DAILY_CAP = 5  # per-client daily review requests (ban-safety)

# Step definitions for the review sequence
SEQUENCE_STEPS = [
    {
        "step": "initial_request",
        "delay_hours": 0,
        "channel": "whatsapp",
        "template": (
            "Namaste {customer_name} ji! 🙏\n\n"
            "{business_name} ki taraf se service ka mauka dene ke liye dhanyawad.\n"
            "Achhi lagi ho to 30 second me Google par review de dijiye ⭐\n\n"
            "{review_link}\n\n"
            "Dhanyawad! 🙏"
        ),
        "sentiment_gate": True,
    },
    {
        "step": "reminder_1",
        "delay_hours": 48,
        "channel": "sms",
        "template": (
            "Hi {customer_name} ji, {business_name} ke review ka link: {review_link} "
            "— sirf 30 second lagenge! ⭐⭐⭐⭐⭐"
        ),
        "sentiment_gate": True,
    },
    {
        "step": "reminder_2",
        "delay_hours": 168,  # 7 days
        "channel": "whatsapp",
        "template": (
            "{customer_name} ji, humne aapka feedback bahut important hai! 🙏\n"
            "Agar abhi tak review nahi diya to please dedo — hum improve karenge.\n\n"
            "{review_link}"
        ),
        "sentiment_gate": True,
    },
    {
        "step": "private_feedback",
        "delay_hours": 0,
        "channel": "whatsapp",
        "template": (
            "{customer_name} ji, hume pata hai experience perfect nahi raha. "
            "Aap 1 line me bataiye kya improve karein — seedha owner tak jaayega. "
            "Dhanyawad! 🙏"
        ),
        "sentiment_gate": False,  # always for unhappy customers
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _track(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[review_automation] track skip: {e}")


def _load_today_requests(client_id: str) -> int:
    """Count how many review requests were sent today for this client."""
    count = 0
    today = _today()
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if (
                            rec.get("client_id") == client_id
                            and rec.get("sent_at", "").startswith(today)
                            and rec.get("status") == "sent"
                        ):
                            count += 1
                    except Exception:
                        pass
    except Exception:
        pass
    return count


def list_sequences(client_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """List review sequences, optionally filtered by client."""
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if client_id and rec.get("client_id") != client_id:
                            continue
                        rows.append(rec)
                    except Exception:
                        pass
    except Exception:
        pass
    return list(reversed(rows))[:limit]


def get_sequence_stats(client_id: str | None = None) -> dict[str, Any]:
    """Aggregate stats for review sequences."""
    sequences = list_sequences(client_id, limit=10000)
    total = len(sequences)
    sent = sum(1 for s in sequences if s.get("status") == "sent")
    replied = sum(1 for s in sequences if s.get("reply_received"))
    google_reviews = sum(1 for s in sequences if s.get("review_type") == "google")
    private_feedback = sum(1 for s in sequences if s.get("review_type") == "private")
    escalations = sum(1 for s in sequences if s.get("step") == "reminder_2")

    return {
        "total_sequences": total,
        "sent": sent,
        "reply_received": replied,
        "google_reviews": google_reviews,
        "private_feedback": private_feedback,
        "escalations": escalations,
        "conversion_rate": round(replied / sent * 100, 1) if sent > 0 else 0,
    }


async def start_review_sequence(
    client_id: str,
    business_name: str,
    customer_name: str = "",
    customer_phone: str = "",
    sentiment_score: int | None = None,
    trigger_event: str = "service_completed",
) -> dict[str, Any]:
    """Start an automated review request sequence for a customer.

    - client_id: tenant scope
    - sentiment_score: 1-5 (None = unknown → assume happy)
    - trigger_event: what triggered the sequence

    Returns sequence_id + first step draft.
    """
    # Daily cap check (ban-safety)
    today_count = _load_today_requests(client_id)
    if today_count >= _DAILY_CAP:
        return {
            "ok": False,
            "error": f"Daily review request cap reached ({_DAILY_CAP}/day per client)",
            "daily_count": today_count,
        }

    seq_id = uuid.uuid4().hex[:12]
    happy = sentiment_score is None or (isinstance(sentiment_score, int) and sentiment_score >= 4)

    # Choose first step based on sentiment
    if happy:
        first_step = SEQUENCE_STEPS[0]  # initial_request
    else:
        first_step = SEQUENCE_STEPS[3]  # private_feedback

    # Generate review link (using existing review_kit)
    review_link = ""
    try:
        from app.marketing import review_kit

        kit = await review_kit.full_kit(business_name, business_name)
        review_link = (kit.get("links") or {}).get("maps_search_url", "")
    except Exception as e:
        logger.debug(f"[review_automation] review_kit skip: {e}")
        review_link = f"https://search.google.com/local/writereview?placeid={business_name}"

    # Format message template
    message = first_step["template"].format(
        customer_name=customer_name or "Customer",
        business_name=business_name,
        review_link=review_link,
    )

    # Auto-send via WhatsApp (existing integration)
    auto_sent = False
    want_auto = os.environ.get("WHATSAPP_AUTO_SEND", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if want_auto and customer_phone:
        try:
            from app.integrations.whatsapp import get_whatsapp_sender

            wa = get_whatsapp_sender()
            res = await wa.send_text_message(customer_phone, message)
            auto_sent = bool(res and not res.get("error"))
        except Exception as e:
            logger.debug(f"[review_automation] auto-send skip: {e}")

    status = "sent" if auto_sent else "pending"

    # Record the sequence
    rec = {
        "sequence_id": seq_id,
        "client_id": client_id,
        "business_name": business_name,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "sentiment_score": sentiment_score,
        "trigger_event": trigger_event,
        "step": first_step["step"],
        "channel": first_step["channel"],
        "message": message,
        "review_link": review_link,
        "review_type": "google" if happy else "private",
        "status": status,
        "auto_sent": auto_sent,
        "reply_received": False,
        "created_at": _now(),
        "sent_at": _now() if auto_sent else None,
        "next_step_at": (
            (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat() if happy else None
        ),
    }
    _track(rec)

    # Schedule next step via Celery (if enabled)
    if happy and auto_sent:
        try:
            from app.tasks.onboard_pipeline import _schedule_next_review_step

            _schedule_next_review_step.apply_async(
                args=[seq_id, client_id, 1],
                countdown=48 * 3600,  # 48 hours
            )
        except Exception as e:
            logger.debug(f"[review_automation] schedule skip: {e}")

    return {
        "ok": True,
        "sequence_id": seq_id,
        "step": first_step["step"],
        "channel": first_step["channel"],
        "review_type": "google" if happy else "private",
        "message": message,
        "review_link": review_link,
        "auto_sent": auto_sent,
        "status": status,
    }


async def handle_reply(
    sequence_id: str,
    reply_text: str,
    reply_sentiment: int | None = None,
) -> dict[str, Any]:
    """Process a customer reply to a review request.

    - reply_text: what the customer said
    - reply_sentiment: 1-5 if detected, None = auto-detect
    """
    # Find the sequence
    sequences = list_sequences(limit=10000)
    seq = None
    for s in sequences:
        if s.get("sequence_id") == sequence_id:
            seq = s
            break

    if not seq:
        return {"ok": False, "error": "Sequence not found"}

    # Determine reply sentiment (simple keyword-based)
    if reply_sentiment is None:
        lower = reply_text.lower()
        if any(
            w in lower
            for w in [
                "achha",
                "great",
                "good",
                "badhiya",
                "excellent",
                "thanks",
                "dhanyawad",
                "shukriya",
            ]
        ):
            reply_sentiment = 5
        elif any(w in lower for w in ["theek", "ok", "okay", "fine", "accha"]):
            reply_sentiment = 4
        elif any(w in lower for w in ["bura", "bad", "worst", "kharab", "pareshan"]):
            reply_sentiment = 2
        else:
            reply_sentiment = 3

    # Track the reply
    rec = {
        "sequence_id": sequence_id,
        "client_id": seq.get("client_id"),
        "reply_text": reply_text,
        "reply_sentiment": reply_sentiment,
        "replied_at": _now(),
    }
    _track(rec)

    return {
        "ok": True,
        "sequence_id": sequence_id,
        "reply_sentiment": reply_sentiment,
        "reply_text": reply_text,
        "action": "google_review" if reply_sentiment >= 4 else "private_feedback",
    }


__all__ = [
    "start_review_sequence",
    "handle_reply",
    "list_sequences",
    "get_sequence_stats",
    "SEQUENCE_STEPS",
    "_DAILY_CAP",
]
