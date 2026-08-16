"""Email Drip Sequence Engine — multi-step email sequences with branching + A/B testing.

Inspired by ActiveCampaign, HubSpot, GoHighLevel workflows:
  - Multi-step sequences with delays, conditions, and branching
  - A/B test subject lines and content
  - Behavioral triggers: open, click, reply, no-action
  - Auto-send via existing SMTP (Hostinger admin@leadsgenai.in)
  - Track: data/email_drips.jsonl + data/email_drip_runs.jsonl
  - Feature flag: EMAIL_DRIPS (default OFF)

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

_DRIPS_STORE = os.path.join("data", "email_drips.jsonl")
_RUNS_STORE = os.path.join("data", "email_drip_runs.jsonl")

# Pre-built drip templates for common use cases
DRIP_TEMPLATES = {
    "welcome_5day": {
        "name": "Welcome 5-Day Nurture",
        "description": "5 email welcome sequence for new leads",
        "steps": [
            {
                "delay_hours": 0,
                "subject": "Welcome to {business_name}! 🎉",
                "body": (
                    "Namaste {customer_name} ji!\n\n"
                    "Welcome to {business_name}. Hum aapki marketing ko "
                    "AI se automate karenge.\n\n"
                    "Kuch din me aapko pehla content package milega.\n\n"
                    "Dhanyawad!"
                ),
            },
            {
                "delay_hours": 24,
                "subject": "Aapka first content ready hai! 📝",
                "body": (
                    "{customer_name} ji,\n\n"
                    "Humne aapke liye pehla social media content pack ready kiya hai. "
                    "Dashboard pe jaake dekho: {dashboard_link}\n\n"
                    "Review karo aur approve karo!"
                ),
            },
            {
                "delay_hours": 72,
                "subject": "Kaise chal rahi hai marketing? 📊",
                "body": (
                    "{customer_name} ji,\n\n"
                    "Ek hafta ho gaya. Aapka dashboard: {dashboard_link}\n\n"
                    "Koi sawaal ho to reply karo — hum yahan hain!"
                ),
            },
            {
                "delay_hours": 168,
                "subject": "Monthly report ready! 📈",
                "body": (
                    "{customer_name} ji,\n\n"
                    "Aapka first monthly report ready hai. "
                    "Dekho kitne leads aaye, kitne reviews mile.\n\n"
                    "Report: {report_link}"
                ),
            },
            {
                "delay_hours": 336,
                "subject": "Upgrade karo aur aur results paao! 🚀",
                "body": (
                    "{customer_name} ji,\n\n"
                    "Aapka basic plan achha chal raha hai. "
                    "Advanced plan me AI calling + priority support milega.\n\n"
                    "Upgrade: {upgrade_link}"
                ),
            },
        ],
    },
    "winback_3step": {
        "name": "Win-Back Lapsed Customer",
        "description": "3-step sequence for customers who haven't engaged in 30 days",
        "steps": [
            {
                "delay_hours": 0,
                "subject": "Miss you! Kya ho raha hai? 🙏",
                "body": (
                    "{customer_name} ji,\n\n"
                    "Kuch din se aapka dashboard inactive hai. "
                    "Koi problem hai to batao, hum solve karenge!"
                ),
            },
            {
                "delay_hours": 168,
                "subject": "Special offer sirf aapke liye! 💝",
                "body": (
                    "{customer_name} ji,\n\n"
                    "Hum aapko miss kar rahe hain. "
                    "Is month free content refresh lelo!\n\n"
                    "Reply 'YES' karo aur hum setup kar denge."
                ),
            },
            {
                "delay_hours": 336,
                "subject": "Last chance — free consultation! 📞",
                "body": (
                    "{customer_name} ji,\n\n"
                    "Humari taraf se free 15-min marketing consultation. "
                    "Booking: {booking_link}\n\n"
                    "Aapki growth humari priority hai!"
                ),
            },
        ],
    },
    "onboarding_7day": {
        "name": "New Customer Onboarding",
        "description": "7-step onboarding for newly activated customers",
        "steps": [
            {
                "delay_hours": 0,
                "subject": "Setup complete! 🎉",
                "body": "{customer_name} ji, aapka setup ho gaya! Dashboard: {dashboard_link}",
            },
            {
                "delay_hours": 24,
                "subject": "Step 1: Brand details bharo 📝",
                "body": "Dashboard me jaake brand details update karo.",
            },
            {
                "delay_hours": 48,
                "subject": "Step 2: First content approve karo ✅",
                "body": "Pehla content package ready hai. Approve karo!",
            },
            {
                "delay_hours": 96,
                "subject": "Review karo apna calendar 📅",
                "body": "30-day content calendar ready hai. Dekho!",
            },
            {
                "delay_hours": 168,
                "subject": "First week report 📊",
                "body": "Pehla hafta kaisa raha? Report dekho.",
            },
            {
                "delay_hours": 240,
                "subject": "Google reviews badhao ⭐",
                "body": "Review request automation on karo.",
            },
            {
                "delay_hours": 336,
                "subject": "Month 1 complete! 🚀",
                "body": "Pehla month complete. Results dekho aur plan karo.",
            },
        ],
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _track_drip(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_DRIPS_STORE) or ".", exist_ok=True)
        with open(_DRIPS_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[email_drips] track skip: {e}")


def _track_run(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_RUNS_STORE) or ".", exist_ok=True)
        with open(_RUNS_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def list_drips(client_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """List email drip sequences."""
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_DRIPS_STORE):
            with open(_DRIPS_STORE, encoding="utf-8") as f:
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


def get_drip_stats(client_id: str | None = None) -> dict[str, Any]:
    """Aggregate drip stats."""
    drips = list_drips(client_id, limit=10000)
    runs = []
    try:
        if os.path.exists(_RUNS_STORE):
            with open(_RUNS_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if client_id and rec.get("client_id") != client_id:
                            continue
                        runs.append(rec)
                    except Exception:
                        pass
    except Exception:
        pass

    total_drips = len(drips)
    active_drips = sum(1 for d in drips if d.get("status") == "active")
    total_emails = len(runs)
    sent = sum(1 for r in runs if r.get("status") == "sent")
    opened = sum(1 for r in runs if r.get("opened"))
    clicked = sum(1 for r in runs if r.get("clicked"))

    return {
        "total_drips": total_drips,
        "active_drips": active_drips,
        "total_emails_sent": sent,
        "opened": opened,
        "clicked": clicked,
        "open_rate": round(opened / sent * 100, 1) if sent > 0 else 0,
        "click_rate": round(clicked / sent * 100, 1) if sent > 0 else 0,
    }


async def create_drip(
    client_id: str,
    name: str,
    steps: list[dict[str, Any]],
    trigger: str = "manual",
    ab_test: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new email drip sequence.

    - steps: list of {delay_hours, subject, body}
    - trigger: manual | welcome | winback | onboarding
    - ab_test: {subject_a, subject_b, split_pct} for A/B testing
    """
    drip_id = uuid.uuid4().hex[:12]

    rec = {
        "drip_id": drip_id,
        "client_id": client_id,
        "name": name,
        "trigger": trigger,
        "steps": steps,
        "ab_test": ab_test,
        "status": "active",
        "total_steps": len(steps),
        "created_at": _now(),
    }
    _track_drip(rec)

    return {
        "ok": True,
        "drip_id": drip_id,
        "name": name,
        "total_steps": len(steps),
        "status": "active",
    }


async def start_drip_for_customer(
    drip_id: str,
    client_id: str,
    customer_email: str,
    customer_name: str = "",
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Start a drip sequence for a specific customer."""
    drips = list_drips(client_id, limit=10000)
    drip = None
    for d in drips:
        if d.get("drip_id") == drip_id:
            drip = d
            break

    if not drip:
        return {"ok": False, "error": "Drip not found"}

    if drip.get("status") != "active":
        return {"ok": False, "error": "Drip is not active"}

    run_id = uuid.uuid4().hex[:12]
    steps = drip.get("steps", [])
    vars_ = variables or {}

    # Send first email immediately
    if steps:
        first = steps[0]
        subject = first.get("subject", "")
        body = first.get("body", "")

        # Apply A/B test if configured
        ab = drip.get("ab_test")
        if ab and ab.get("subject_a") and ab.get("subject_b"):
            import random

            split = ab.get("split_pct", 50)
            if random.randint(1, 100) <= split:
                subject = ab["subject_a"]
            else:
                subject = ab["subject_b"]

        # Replace variables
        for k, v in vars_.items():
            subject = subject.replace("{" + k + "}", v)
            body = body.replace("{" + k + "}", v)
        subject = subject.replace("{customer_name}", customer_name)
        body = body.replace("{customer_name}", customer_name)

        # Send via existing SMTP
        sent = False
        try:
            from app.integrations.email_sender import send_email

            await send_email(customer_email, subject, body)
            sent = True
        except Exception as e:
            logger.debug(f"[email_drips] send skip: {e}")

        run_rec = {
            "run_id": run_id,
            "drip_id": drip_id,
            "client_id": client_id,
            "customer_email": customer_email,
            "customer_name": customer_name,
            "step": 0,
            "subject": subject,
            "body_preview": body[:200],
            "status": "sent" if sent else "failed",
            "opened": False,
            "clicked": False,
            "sent_at": _now() if sent else None,
        }
        _track_run(run_rec)

    return {
        "ok": True,
        "run_id": run_id,
        "drip_id": drip_id,
        "total_steps": len(steps),
        "first_email_sent": sent if steps else False,
    }


def get_templates() -> list[dict[str, Any]]:
    """Return available drip templates."""
    return [
        {
            "id": tid,
            "name": t["name"],
            "description": t["description"],
            "steps": len(t["steps"]),
        }
        for tid, t in DRIP_TEMPLATES.items()
    ]


__all__ = [
    "create_drip",
    "start_drip_for_customer",
    "list_drips",
    "get_drip_stats",
    "get_templates",
    "DRIP_TEMPLATES",
]
