"""Auto-proposal / quote generator — per-lead personalized sales proposal.

Interested lead → AI ek ready proposal banata: problem → solution → plan+pricing →
ROI (missed-revenue calc) → demo-link + payment-link. 1-click send / self-serve close.

Reuse: packages (pricing), lead_tools (ROI), free_ai (polish). Ban-safe (content +
links; payment self-serve via /pricing). Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

BASE = "https://leadsgenai.in"

# Fallback only — live prices ALWAYS prefer get_public_packages() (billing truth).
# Legacy "growth" is intentionally mapped → starter so sales assets never quote ₹2,999.
PLANS = {
    "starter": {
        "name": "AI Marketing Automation",
        "price": 1999,
        "for": "posts, GBP, festivals, WhatsApp content, lead capture",
        "key": "starter",
    },
    "advanced": {
        "name": "Combo — Marketing + AI Voice",
        "price": 5999,
        "for": "marketing + AI voice callback feature (500 min/mo)",
        "key": "advanced",
    },
}


def _plan(plan_key: str) -> dict[str, Any]:
    """Resolve a public plan. Legacy `growth` → starter (hidden plan must not leak)."""
    key = (plan_key or "starter").strip().lower() or "starter"
    if key == "growth":
        key = "starter"
    try:
        from app.marketing.packages import get_public_packages

        for p in get_public_packages():
            if str(p.get("key") or "").strip().lower() != key:
                continue
            price = int(p.get("price_inr_month") or 0)
            if price <= 0:
                break
            return {
                "key": key,
                "name": str(p.get("name") or key.title()),
                "price": price,
                "for": str(p.get("tagline") or p.get("blurb") or "")[:160],
            }
    except Exception as exc:
        logger.debug("[proposal] packages resolve skip: %s", exc)
    return dict(PLANS.get(key) or PLANS["starter"])


async def generate_proposal(
    business_name: str,
    niche: str = "general",
    city: str = "",
    plan: str = "starter",
    missed_per_day: float = 5,
    avg_deal_value: float = 20000,
    phone: str = "",
) -> dict[str, Any]:
    """Ek lead ke liye personalized proposal + payment/demo links + ROI. Kabhi raise nahi.

    `phone` (optional) ho to memory_vault history LLM prompt me jaati (proposal
    prospect ki actual baat-cheet pe personalized) — memory na ho = aaj jaisa."""
    biz = (business_name or "Aapka business").strip()
    p = _plan(plan)

    # Best-effort memory context (never-raise; empty = zero change)
    history = ""
    if phone:
        try:
            from app.platform import memory_vault

            history = memory_vault.context_snippet(phone=phone, max_chars=600)
        except Exception:
            history = ""

    # ROI from lead_tools (missed-revenue)
    roi = {}
    try:
        from app.marketing import lead_tools

        roi = lead_tools.missed_call_revenue(missed_per_day, avg_deal_value)
    except Exception:
        pass
    lost = roi.get("lost_per_month", 0)

    template = (
        f"*Proposal for {biz}*\n\n"
        f"Problem: {(niche or 'aapke').replace('_', ' ')} business me aadhe inquiries bina follow-up "
        f"ke nikal jaate — ~₹{lost:,}/mo ka nuksan.\n\n"
        f"Solution: LeadGen AI marketing automation — posts/GBP/reviews/WhatsApp drafts. "
        f"Advanced plan me AI voice callback feature bhi. Aap ready leads pe focus karo.\n\n"
        f"Plan: *{p['name']} — ₹{p['price']}/mo* ({p['for']}). Cancel anytime.\n\n"
        f"2-min live demo: {BASE}/app/test-call\n"
        f"Shuru karein (UPI pay): {BASE}/pricing\n\n"
        f"— Sumit, LeadGen AI"
    )

    proposal = template
    try:
        from app.voice_agent import free_ai

        sys = (
            "Tum ek B2B sales-proposal writer ho (India). Ek SHORT (6-8 line) Hinglish proposal "
            "likho: problem (ROI loss) → solution → plan+price → demo+pay link. "
            "Confident par pushy nahi. Sirf proposal text. Card/netbanking mat bolo — UPI primary."
        )
        prompt = (
            f"Business: {biz}, Niche: {niche}, City: {city}. Plan: {p['name']} ₹{p['price']}/mo. "
            f"Monthly loss: ₹{lost}. Demo: {BASE}/app/test-call. Pay: {BASE}/pricing."
        )
        if history:
            prompt += f"\nIs prospect ki history (personalize karo): {history}"
        txt, _ = await free_ai.chat(
            sys, [{"role": "user", "content": prompt}], max_tokens=320, temperature=0.6
        )
        if txt and txt.strip():
            proposal = txt.strip()
    except Exception as e:
        logger.debug(f"[proposal] llm skip: {e}")

    return {
        "ok": True,
        "business_name": biz,
        "plan": p["name"],
        "plan_key": p.get("key") or "starter",
        "price_inr": p["price"],
        "monthly_loss_inr": lost,
        "proposal": proposal,
        "demo_link": f"{BASE}/app/test-call",
        "payment_link": f"{BASE}/pricing",
        "auto_sent": False,
    }


__all__ = ["generate_proposal", "PLANS", "_plan"]
