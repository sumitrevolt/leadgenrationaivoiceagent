"""
Customer Plugins / AI Capabilities API
=======================================
GET /api/customer/plugins  → active AI capabilities for this customer

Auth: require_customer (JWT from customer portal).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth_deps import require_customer
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/customer", tags=["Customer Plugins"])


# -----------------------------------------------------------------------
# Response models
# -----------------------------------------------------------------------


class Capability(BaseModel):
    """A single AI capability for the customer."""

    id: str
    title: str
    desc: str = ""
    icon: str = "🔧"
    active: bool = True
    planned: bool = False
    features: list[str] = Field(default_factory=list)
    link: str = ""


class CustomerPluginsResponse(BaseModel):
    """Customer's AI capabilities response."""

    ok: bool = True
    plan: str = ""
    product: str = ""
    capabilities: list[Capability] = Field(default_factory=list)
    timestamp: float = 0.0


# -----------------------------------------------------------------------
# Capability definitions per product
# -----------------------------------------------------------------------

_MARKETING_CAPABILITIES = [
    Capability(
        id="content_creation",
        title="AI Content Creation",
        desc="Aapke business ke liye automatically social media posts, banners, aur content banta hai — daily.",
        icon="📝",
        features=[
            "Daily social media posts",
            "Festival & event-based content",
            "Business-specific text & images",
            "Instagram, Facebook, Google Business par ready",
        ],
        link="/app/customer",
    ),
    Capability(
        id="lead_management",
        title="Lead Management",
        desc="Jo log aapki website ya ads se inquiry karte hain, unhe automatically track karta hai.",
        icon="📋",
        features=[
            "Website se leads auto-capture",
            "Lead score aur priority",
            "Hot leads pe turant notification",
            "CSV import bhi kar sakte ho",
        ],
        link="/app/customer/pipeline",
    ),
    Capability(
        id="marketing_calendar",
        title="Marketing Calendar",
        desc="Poora mahine ka content plan automatically ban jata hai — approve karo aur publish ho jayega.",
        icon="📅",
        features=[
            "30-day content calendar",
            "Festival-aware scheduling",
            "Auto-publish (admin approval ke baad)",
            "Performance tracking",
        ],
        link="/app/customer",
    ),
    Capability(
        id="website_seo",
        title="Website SEO & Optimization",
        desc="Aapki website ko Google pe better rank dilane ke liye AI suggestions milte hain.",
        icon="🌐",
        features=[
            "SEO audit aur suggestions",
            "Google Business profile optimization",
            "Content recommendations",
            "Performance monitoring",
        ],
        link="/app/customer",
    ),
    Capability(
        id="ai_assistant",
        title="AI Business Assistant",
        desc="Aapke customer ke sawalon ka AI jawab deta hai — 24/7, turant.",
        icon="🤖",
        features=[
            "Customer queries ka instant reply",
            "Business knowledge base",
            "Smart routing",
            "Human handoff jab zarurat ho",
        ],
        link="/app/customer",
    ),
    Capability(
        id="analytics",
        title="Analytics & Reporting",
        desc="Aapka marketing kitna kaam kar raha hai — ye sab data dikhta hai.",
        icon="📊",
        features=[
            "Lead conversion tracking",
            "Content performance",
            "Campaign ROI",
            "Monthly report",
        ],
        link="/app/customer",
    ),
    Capability(
        id="review_management",
        title="Review Management",
        desc="Google reviews track karta hai aur response suggestions deta hai.",
        icon="⭐",
        features=[
            "New review alerts",
            "AI-generated reply suggestions",
            "Sentiment tracking",
            "Review push campaigns",
        ],
        link="/app/customer",
    ),
    Capability(
        id="email_outreach",
        title="Email Outreach",
        desc="Potential customers ko automatically email karta hai — personalized, smart.",
        icon="📧",
        features=[
            "Cold email sequences",
            "Follow-up automation",
            "Reply tracking",
            "Deliverability monitoring",
        ],
        link="/app/customer",
    ),
]

_VOICE_CAPABILITIES = [
    Capability(
        id="ai_calling",
        title="AI Voice Calling",
        desc="AI-powered telecaller jo automatically calls karta hai — 24/7, multilingual.",
        icon="📞",
        features=[
            "Automated outbound calling",
            "Multi-language support (Hindi, English, etc.)",
            "Call recording aur transcription",
            "Smart follow-up scheduling",
        ],
        link="/app/customer",
    ),
    Capability(
        id="call_analytics",
        title="Call Analytics",
        desc="Har call ka data — kisne kaha kya, kitni der baat hui, interest level.",
        icon="📊",
        features=[
            "Call duration aur outcome tracking",
            "Sentiment analysis",
            "Conversion funnel",
            "Lead scoring from calls",
        ],
        link="/app/customer",
    ),
    Capability(
        id="lead_management",
        title="Lead Management",
        desc="Jo log call karte ya message karte hain, unhe automatically track karta hai.",
        icon="📋",
        features=[
            "Auto-lead capture from calls",
            "Lead score aur priority",
            "Hot leads pe turant notification",
            "CRM integration ready",
        ],
        link="/app/customer/pipeline",
    ),
    Capability(
        id="ai_assistant",
        title="AI Receptionist",
        desc="Incoming calls ka AI jawab deta hai — greet, route, message, book.",
        icon="🤖",
        features=[
            "24/7 call answering",
            "Department routing",
            "Appointment booking",
            "Message forwarding to owner",
        ],
        link="/app/customer",
    ),
]


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _get_client_product(client_id: str) -> tuple[str, str]:
    """Get customer's product and plan name."""
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(client_id)
        if not client:
            return "marketing", "Starter"
        product = client.get("product", "marketing")
        plan = client.get("plan", "starter")
        return product, plan
    except Exception:
        return "marketing", "Starter"


def _get_active_capabilities(client_id: str) -> list[Capability]:
    """Determine which capabilities are active for this customer."""
    product, plan = _get_client_product(client_id)

    if product == "voice":
        caps = list(_VOICE_CAPABILITIES)
    elif product == "combo":
        caps = list(_MARKETING_CAPABILITIES) + [
            c for c in _VOICE_CAPABILITIES if c.id not in {mc.id for mc in _MARKETING_CAPABILITIES}
        ]
    else:
        caps = list(_MARKETING_CAPABILITIES)

    # Check which features are actually enabled via flags
    flag_map = {
        "content_creation": "AUTO_CONTENT",
        "lead_management": None,  # always active
        "marketing_calendar": "AUTO_CONTENT",
        "website_seo": None,  # always active
        "ai_assistant": "REPLY_AGENT",
        "analytics": None,  # always active
        "review_management": "REVIEW_MONITOR",
        "email_outreach": "AUTO_EMAIL_OUTREACH",
        "ai_calling": "VOICE_LAUNCH_CAMPAIGN",
        "call_analytics": None,  # always active
    }

    for cap in caps:
        flag = flag_map.get(cap.id)
        if flag:
            cap.active = _flag(flag)
        else:
            cap.active = True  # core features always active

    return caps


# -----------------------------------------------------------------------
# Endpoint
# -----------------------------------------------------------------------


@router.get("/plugins", response_model=CustomerPluginsResponse)
async def customer_plugins(
    client_id: str = Depends(require_customer),
) -> CustomerPluginsResponse:
    """Get active AI capabilities for this customer.

    Shows which features are active, dormant, or planned.
    Uses simple language (Hinglish) for the customer.
    """
    import time

    product, plan = _get_client_product(client_id)
    capabilities = _get_active_capabilities(client_id)

    return CustomerPluginsResponse(
        ok=True,
        plan=plan.title(),
        product=product,
        capabilities=capabilities,
        timestamp=time.time(),
    )
