"""Sales Autopilot message generation — verified public fields only, no fake claims.

Deterministic template families keyed by ``(channel, step)``. Templates interpolate ONLY
whitelisted, verified fields (business name, city, niche) — never invented metrics, fake
social proof, or unverifiable guarantees. Product truth: the entry Marketing plan is the
**Starter at ₹1,999/mo** (single billing source). Every generated message carries a
content hash + template version + validation status for audit + idempotency keys.

Never raises; on any error returns a minimal safe opt-out-friendly message.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

TEMPLATE_VERSION = "2026-07-24.1"

# Product truth (do not drift; billing single-source = packages.py Starter).
STARTER_PRICE_INR = 1999
STARTER_NAME = "Starter"

# Whitelisted interpolation fields — anything else is dropped.
_ALLOWED_FIELDS = ("name", "city", "niche")

_OPT_OUT_LINE = "Reply STOP to opt out anytime."


def _safe_field(prospect: dict[str, Any], key: str, default: str = "") -> str:
    val = str((prospect or {}).get(key) or default).strip()
    # Guard against template-injection / control chars in names.
    return val.replace("{", "").replace("}", "")[:80]


def _niche_label(niche: str) -> str:
    return (niche or "local business").replace("_", " ").strip() or "local business"


# ------------------------------------------------------------------ #
# Template families
# ------------------------------------------------------------------ #
def _initial_whatsapp(p: dict[str, Any]) -> str:
    name = _safe_field(p, "name", "there")
    niche = _niche_label(_safe_field(p, "niche"))
    return (
        f"Hi {name}, this is LeadsGenAI. We help {niche} businesses get more customers "
        f"with AI-run marketing (social posts, replies, follow-ups) — done for you. "
        f"Our {STARTER_NAME} plan is Rs {STARTER_PRICE_INR}/month. "
        f"Would a quick 2-minute demo be useful? {_OPT_OUT_LINE}"
    )


def _initial_email(p: dict[str, Any]) -> tuple[str, str]:
    name = _safe_field(p, "name", "there")
    city = _safe_field(p, "city")
    niche = _niche_label(_safe_field(p, "niche"))
    where = f" in {city}" if city else ""
    subject = f"More customers for {name}?" if name != "there" else "More customers, AI-run"
    body = (
        f"Hi {name},\n\n"
        f"I'm reaching out from LeadsGenAI. We run marketing for {niche} businesses{where} "
        f"— AI creates the content, handles replies, and follows up with leads, so you don't have to.\n\n"
        f"Our {STARTER_NAME} plan starts at Rs {STARTER_PRICE_INR}/month. "
        f"Happy to show you a 2-minute demo — just reply and I'll send a link.\n\n"
        f"— Team LeadsGenAI\n{_OPT_OUT_LINE}"
    )
    return subject, body


def _followup_1(p: dict[str, Any]) -> str:
    name = _safe_field(p, "name", "there")
    return (
        f"Hi {name}, just following up on my note about AI-run marketing for your business. "
        f"No pressure — reply DEMO for a quick 2-min walkthrough, or STOP to opt out."
    )


def _followup_2(p: dict[str, Any]) -> str:
    name = _safe_field(p, "name", "there")
    return (
        f"Hi {name}, last note from me — if getting more customers on autopilot sounds useful, "
        f"reply DEMO and I'll share details. Otherwise no worries. {_OPT_OUT_LINE}"
    )


def _demo(p: dict[str, Any]) -> str:
    return (
        "Great! Here's a 2-minute demo of how LeadsGenAI runs your marketing: "
        "https://leadsgenai.in/demo — reply with any question."
    )


def _pricing(p: dict[str, Any]) -> str:
    return (
        f"Our {STARTER_NAME} plan is Rs {STARTER_PRICE_INR}/month (AI content, replies & follow-ups). "
        f"Full details: https://leadsgenai.in/pricing"
    )


def _optout_ack(p: dict[str, Any]) -> str:
    return "Done — you won't hear from us again. Thank you, and all the best!"


# family -> builder. Email family returns (subject, body); others return body only.
_FAMILIES = {
    ("whatsapp", "initial"): _initial_whatsapp,
    ("email", "initial"): _initial_email,
    ("whatsapp", "followup_1"): _followup_1,
    ("whatsapp", "followup_2"): _followup_2,
    ("email", "followup_1"): _followup_1,
    ("email", "followup_2"): _followup_2,
    ("whatsapp", "demo"): _demo,
    ("whatsapp", "pricing"): _pricing,
    ("whatsapp", "optout_ack"): _optout_ack,
}


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def build(prospect: dict[str, Any], *, channel: str, step: str) -> dict[str, Any]:
    """Return a message envelope: body/subject + template family + version + hash.

    ``validation_status`` here is ``generated`` — the deterministic safety validator
    (:mod:`.safety`) sets the final AUTO_APPROVED/AUTO_REJECTED status.
    """
    channel = (channel or "").lower()
    step = (step or "").lower()
    try:
        builder = _FAMILIES.get((channel, step))
        if builder is None:
            # Fall back to a channel-appropriate follow-up rather than inventing content.
            builder = _FAMILIES.get((channel, "followup_1")) or _followup_1
        out = builder(prospect or {})
        subject = ""
        if isinstance(out, tuple):
            subject, body = out
        else:
            body = out
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.messages] build failed: %s", e)
        subject, body = "", _optout_ack(prospect or {})
    family = f"{channel}:{step}"
    return {
        "channel": channel,
        "step": step,
        "template_family": family,
        "template_version": TEMPLATE_VERSION,
        "subject": subject,
        "body": body,
        "content_hash": content_hash(body),
        "validation_status": "generated",
    }


__all__ = [
    "TEMPLATE_VERSION",
    "STARTER_PRICE_INR",
    "STARTER_NAME",
    "content_hash",
    "build",
]
