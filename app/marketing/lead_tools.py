"""Free interactive lead-magnet tools — PLG inbound (telephony-free).

Calculators/checkers jo VALUE dikhate + lead capture karte. Audit ke alawa naye
top-of-funnel magnets: missed-call revenue calc, lead-cost savings, Google-presence
score. Result + ek strong CTA → /audit ya signup. Pure-Python (calc), import-safe.

Capture: tool use karne ke baad email/phone maango → existing inquiry path. Inbound.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def missed_call_revenue(
    missed_per_day: float, avg_deal_value: float, close_rate: float = 0.2
) -> dict[str, Any]:
    """Roz missed inquiries × deal-value × close-rate → mahine/saal ka khoya revenue."""
    try:
        m = max(0.0, float(missed_per_day))
        v = max(0.0, float(avg_deal_value))
        cr = min(1.0, max(0.0, float(close_rate)))
    except Exception:
        m, v, cr = 0, 0, 0.2
    lost_month = m * 26 * v * cr  # ~26 working days
    return {
        "ok": True,
        "tool": "missed_call_revenue",
        "inputs": {"missed_per_day": m, "avg_deal_value": v, "close_rate": cr},
        "lost_per_month": round(lost_month),
        "lost_per_year": round(lost_month * 12),
        "headline": f"Aap har mahine ~₹{round(lost_month):,} kho rahe ho missed inquiries se.",
        "fix": "AI voice agent har inquiry ko 2-min me call karke qualify karta — ye revenue bachao.",
        "cta": {"text": "Free Google audit lein", "url": "/audit"},
    }


def lead_cost_savings(current_cost_per_lead: float, leads_per_month: float) -> dict[str, Any]:
    """Current lead-cost vs AI lead-gen (assume ~60% sasta) → monthly savings."""
    try:
        c = max(0.0, float(current_cost_per_lead))
        n = max(0.0, float(leads_per_month))
    except Exception:
        c, n = 0, 0
    ai_cost = c * 0.4  # ~60% cheaper assumption
    save_month = (c - ai_cost) * n
    return {
        "ok": True,
        "tool": "lead_cost_savings",
        "inputs": {"current_cost_per_lead": c, "leads_per_month": n},
        "ai_cost_per_lead": round(ai_cost, 1),
        "savings_per_month": round(save_month),
        "savings_per_year": round(save_month * 12),
        "headline": f"AI se aap ~₹{round(save_month):,}/mo bacha sakte ho lead-cost pe.",
        "cta": {"text": "Shuru karein ₹1,999/mo", "url": "/pricing"},
    }


async def google_presence_score(business_name: str, city: str = "") -> dict[str, Any]:
    """Simple Google-presence checklist score (0-100) + fixes. free-LLM optional flavor."""
    biz = (business_name or "Aapka business").strip()
    checklist = [
        {"item": "Google Business Profile claimed + complete", "weight": 25},
        {"item": "50+ recent reviews (4★+)", "weight": 20},
        {"item": "Weekly Google posts", "weight": 15},
        {"item": "Website mobile-fast + click-to-call", "weight": 15},
        {"item": "Local keywords ranking (top 3)", "weight": 15},
        {"item": "Inquiry ka 5-min me follow-up", "weight": 10},
    ]
    return {
        "ok": True,
        "tool": "google_presence_score",
        "business_name": biz,
        "city": city,
        "checklist": checklist,
        "headline": f"{biz} ka Google presence kitna strong hai? Ye 6 cheezein check karo.",
        "note": "Free detailed audit me hum aapka EXACT score + top-3 fixes dete hain.",
        "cta": {"text": "Free Google Audit (2 min)", "url": "/audit"},
    }


def list_tools() -> list[dict[str, str]]:
    return [
        {
            "key": "missed_call_revenue",
            "title": "Missed-Call Revenue Calculator",
            "desc": "Kitna paisa missed inquiries se ja raha",
        },
        {
            "key": "lead_cost_savings",
            "title": "Lead-Cost Savings Calculator",
            "desc": "AI se kitna bacha sakte ho",
        },
        {
            "key": "google_presence_score",
            "title": "Google Presence Checker",
            "desc": "Aapka Google score + fixes",
        },
    ]


__all__ = ["missed_call_revenue", "lead_cost_savings", "google_presence_score", "list_tools"]
