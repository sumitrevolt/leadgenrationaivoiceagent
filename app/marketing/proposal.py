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
PLANS = {
    "starter": {
        "name": "Starter",
        "price": 1199,
        "for": "marketing only (posts, GBP, reviews, WhatsApp)",
    },
    "growth": {
        "name": "Growth",
        "price": 2999,
        "for": "+ content calendar, competitor, lead-form, monthly report",
    },
    "advanced": {
        "name": "Advanced",
        "price": 6999,
        "for": "+ AI voice agent (inquiry call 2-min, qualification, 500 min/mo)",
    },
}


def _plan(plan_key: str) -> dict[str, Any]:
    return PLANS.get((plan_key or "growth").strip().lower(), PLANS["growth"])


async def generate_proposal(
    business_name: str,
    niche: str = "general",
    city: str = "",
    plan: str = "growth",
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
        f"Problem: {(niche or 'aapke').replace('_',' ')} business me aadhe inquiries bina follow-up "
        f"ke nikal jaate — ~₹{lost:,}/mo ka nuksan.\n\n"
        f"Solution: LeadGen AI har inquiry ko 2-min me AI se call karke qualify karta + marketing/"
        f"Google/reviews automate. Aap sirf ready leads pe focus karo.\n\n"
        f"Plan: *{p['name']} — ₹{p['price']}/mo* ({p['for']}). Pehle 10 leads FREE. Cancel anytime.\n\n"
        f"2-min live demo: {BASE}/app/test-call\n"
        f"Shuru karein (online pay): {BASE}/pricing\n\n"
        f"— Sumit, LeadGen AI"
    )

    proposal = template
    try:
        from app.voice_agent import free_ai

        sys = (
            "Tum ek B2B sales-proposal writer ho (India). Ek SHORT (6-8 line) Hinglish proposal "
            "likho: problem (ROI loss) → solution → plan+price → free-trial → demo+pay link. "
            "Confident par pushy nahi. Sirf proposal text."
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
        "price_inr": p["price"],
        "monthly_loss_inr": lost,
        "proposal": proposal,
        "demo_link": f"{BASE}/app/test-call",
        "payment_link": f"{BASE}/pricing",
        "auto_sent": False,
    }


__all__ = ["generate_proposal", "PLANS"]
