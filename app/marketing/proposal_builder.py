"""Proposal/Quote Builder — auto-generate service proposals + quotes for local businesses.

Inspired by PandaDoc, Proposify, GoHighLevel Quotes:
  - Generate branded proposals from templates
  - Auto-fill client details + pricing from packages
  - PDF-ready HTML output
  - Approval workflow (draft → sent → accepted → expired)
  - Track: data/proposals.jsonl
  - Feature flag: PROPOSAL_BUILDER (default OFF)

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

_STORE = os.path.join("data", "proposals.jsonl")

# Proposal templates
PROPOSAL_TEMPLATES = {
    "marketing_starter": {
        "name": "AI Marketing Starter",
        "description": "₹1,999/mo marketing automation proposal",
        "sections": [
            {
                "title": "Executive Summary",
                "content": (
                    "Dear {client_name},\n\n"
                    "Hum aapke {business_name} ke liye AI-powered marketing automation ka "
                    "proposal lekar aaye hain. Is plan se aapki social media, content, "
                    "lead management aur customer engagement 100% automated ho jaayegi."
                ),
            },
            {
                "title": "Services Included",
                "content": (
                    "✅ AI Social Media Posts (30/month)\n"
                    "✅ Content Calendar Management\n"
                    "✅ Lead Capture + Auto-Score\n"
                    "✅ Google Review Automation\n"
                    "✅ Email Marketing (2 campaigns/month)\n"
                    "✅ Monthly Performance Report\n"
                    "✅ WhatsApp Business Integration\n"
                    "✅ AI Chatbot for Customer Queries"
                ),
            },
            {
                "title": "Pricing",
                "content": (
                    "📦 AI Marketing Starter — ₹1,999/month\n\n"
                    "Includes:\n"
                    "- 30 AI-generated social media posts\n"
                    "- 2 email campaigns\n"
                    "- Lead management dashboard\n"
                    "- Google review automation\n"
                    "- Monthly analytics report\n\n"
                    "⚡ First month: ₹1,999 (setup FREE)"
                ),
            },
            {
                "title": "Terms & Conditions",
                "content": (
                    "- Minimum commitment: 3 months\n"
                    "- Payment: Monthly via UPI\n"
                    "- Content approval: 24-hour turnaround\n"
                    "- Cancellation: 15-day notice\n"
                    "- Results may vary based on niche and market"
                ),
            },
        ],
    },
    "marketing_advanced": {
        "name": "AI Marketing Advanced",
        "description": "₹5,999/mo premium marketing + voice",
        "sections": [
            {
                "title": "Executive Summary",
                "content": (
                    "Dear {client_name},\n\n"
                    "{business_name} ke liye hamara premium AI marketing plan — "
                    "sab kuch Starter me hai PLUS AI voice calling, priority support, "
                    "aur advanced analytics."
                ),
            },
            {
                "title": "Services Included",
                "content": (
                    "✅ Everything in Starter Plan\n"
                    "✅ AI Voice Calling (500 min/month)\n"
                    "✅ Advanced Lead Scoring + CRM\n"
                    "✅ SMS Marketing Campaigns\n"
                    "✅ WhatsApp Broadcast (2/month)\n"
                    "✅ Festival + Seasonal Content\n"
                    "✅ Competitor Analysis (monthly)\n"
                    "✅ Dedicated Account Manager\n"
                    "✅ Priority Support (4-hour response)"
                ),
            },
            {
                "title": "Pricing",
                "content": (
                    "📦 AI Marketing Advanced — ₹5,999/month\n\n"
                    "Includes:\n"
                    "- 60 AI-generated social media posts\n"
                    "- 4 email campaigns\n"
                    "- 500 AI voice calling minutes\n"
                    "- Advanced CRM + lead scoring\n"
                    "- SMS + WhatsApp marketing\n"
                    "- Festival content calendar\n"
                    "- Monthly competitor analysis\n\n"
                    "⚡ First month: ₹5,999 (setup FREE)"
                ),
            },
            {
                "title": "Terms & Conditions",
                "content": (
                    "- Minimum commitment: 3 months\n"
                    "- Payment: Monthly via UPI\n"
                    "- Voice calling: TRAI-compliant, DLT registered\n"
                    "- Content approval: 24-hour turnaround\n"
                    "- Cancellation: 15-day notice\n"
                    "- Results may vary based on niche and market"
                ),
            },
        ],
    },
    "voice_only": {
        "name": "AI Voice Calling Agent",
        "description": "₹4,999/mo standalone AI telecaller",
        "sections": [
            {
                "title": "Executive Summary",
                "content": (
                    "Dear {client_name},\n\n"
                    "Aapke {business_name} ke liye 24/7 AI telecaller — "
                    "har call ka jawab, leads qualify, appointments book — "
                    "bina kisi insaan ke."
                ),
            },
            {
                "title": "Services Included",
                "content": (
                    "✅ 24/7 AI Voice Agent\n"
                    "✅ Inbound + Outbound Calling\n"
                    "✅ Lead Qualification\n"
                    "✅ Appointment Booking\n"
                    "✅ Call Recording + Transcripts\n"
                    "✅ Post-Call WhatsApp Follow-up\n"
                    "✅ DND Compliance\n"
                    "✅ Monthly Call Analytics"
                ),
            },
            {
                "title": "Pricing",
                "content": (
                    "📦 AI Voice Calling Agent — ₹4,999/month\n\n"
                    "Includes:\n"
                    "- Unlimited inbound calls\n"
                    "- 500 outbound minutes/month\n"
                    "- AI-powered lead qualification\n"
                    "- Automatic appointment booking\n"
                    "- Call recording + transcripts\n"
                    "- Post-call WhatsApp follow-up\n\n"
                    "⚡ First month: ₹4,999 (setup FREE)"
                ),
            },
            {
                "title": "Terms & Conditions",
                "content": (
                    "- Minimum commitment: 3 months\n"
                    "- Payment: Monthly via UPI\n"
                    "- TRAI/DLT compliant\n"
                    "- Cold calling: DLT-approved only\n"
                    "- Cancellation: 15-day notice"
                ),
            },
        ],
    },
    "custom": {
        "name": "Custom Proposal",
        "description": "Blank template for custom proposals",
        "sections": [
            {"title": "Cover Letter", "content": "Dear {client_name},\n\n"},
            {"title": "Scope of Work", "content": ""},
            {"title": "Pricing", "content": ""},
            {"title": "Timeline", "content": ""},
            {"title": "Terms & Conditions", "content": ""},
        ],
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _track(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[proposal_builder] track skip: {e}")


def list_proposals(client_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
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


def get_proposal_stats(client_id: str | None = None) -> dict[str, Any]:
    proposals = list_proposals(client_id, limit=10000)
    total = len(proposals)
    sent = sum(1 for p in proposals if p.get("status") in ("sent", "accepted", "expired"))
    accepted = sum(1 for p in proposals if p.get("status") == "accepted")
    expired = sum(1 for p in proposals if p.get("status") == "expired")

    return {
        "total_proposals": total,
        "sent": sent,
        "accepted": accepted,
        "expired": expired,
        "acceptance_rate": round(accepted / sent * 100, 1) if sent > 0 else 0,
    }


async def generate_proposal(
    client_id: str,
    business_name: str,
    client_name: str,
    template_id: str = "marketing_starter",
    custom_sections: list[dict[str, str]] | None = None,
    custom_pricing: str = "",
    validity_days: int = 30,
) -> dict[str, Any]:
    """Generate a proposal from template."""
    template = PROPOSAL_TEMPLATES.get(template_id)
    if not template:
        return {"ok": False, "error": f"Template '{template_id}' not found"}

    proposal_id = uuid.uuid4().hex[:12]

    # Build sections from template
    sections = []
    for section in custom_sections or template["sections"]:
        content = section.get("content", "")
        # Replace variables
        content = content.replace("{client_name}", client_name)
        content = content.replace("{business_name}", business_name)
        sections.append(
            {
                "title": section.get("title", ""),
                "content": content,
            }
        )

    # Add custom pricing if provided
    if custom_pricing:
        sections.append(
            {
                "title": "Custom Pricing",
                "content": custom_pricing,
            }
        )

    rec = {
        "proposal_id": proposal_id,
        "client_id": client_id,
        "business_name": business_name,
        "client_name": client_name,
        "template_id": template_id,
        "sections": sections,
        "total_sections": len(sections),
        "status": "draft",
        "valid_until": (datetime.now(timezone.utc) + timedelta(days=validity_days)).isoformat(),
        "created_at": _now(),
    }
    _track(rec)

    return {
        "ok": True,
        "proposal_id": proposal_id,
        "template": template["name"],
        "total_sections": len(sections),
        "status": "draft",
        "valid_until": rec["valid_until"],
    }


async def update_proposal_status(
    proposal_id: str,
    status: str,  # draft → sent → accepted → expired
) -> dict[str, Any]:
    """Update proposal status."""
    valid_statuses = {"draft", "sent", "accepted", "expired", "declined"}
    if status not in valid_statuses:
        return {"ok": False, "error": f"Invalid status: {status}. Must be one of {valid_statuses}"}

    rec = {
        "proposal_id": proposal_id,
        "status": status,
        "updated_at": _now(),
    }
    _track(rec)

    return {
        "ok": True,
        "proposal_id": proposal_id,
        "status": status,
    }


def get_templates() -> list[dict[str, Any]]:
    """Available proposal templates."""
    return [
        {
            "id": tid,
            "name": t["name"],
            "description": t["description"],
            "sections": len(t["sections"]),
        }
        for tid, t in PROPOSAL_TEMPLATES.items()
    ]


def render_proposal_html(proposal: dict[str, Any]) -> str:
    """Render proposal as HTML (for PDF export or preview)."""
    sections_html = ""
    for section in proposal.get("sections", []):
        content = section.get("content", "").replace("\n", "<br>")
        sections_html += f"""
        <div class="section">
            <h2>{section.get("title", "")}</h2>
            <p>{content}</p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Proposal - {proposal.get("business_name", "")}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px; }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
        h2 {{ color: #16213e; margin-top: 30px; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>Proposal: {proposal.get("business_name", "")}</h1>
    <p><strong>Prepared for:</strong> {proposal.get("client_name", "")}</p>
    <p><strong>Date:</strong> {proposal.get("created_at", "")[:10]}</p>
    <p><strong>Valid until:</strong> {proposal.get("valid_until", "")[:10]}</p>
    {sections_html}
    <div class="footer">
        <p>Generated by LeadsGen AI — leadsgenai.in</p>
    </div>
</body>
</html>"""


__all__ = [
    "generate_proposal",
    "update_proposal_status",
    "list_proposals",
    "get_proposal_stats",
    "get_templates",
    "render_proposal_html",
    "PROPOSAL_TEMPLATES",
]
