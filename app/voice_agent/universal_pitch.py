"""Universal LeadGen AI voice agent pitch — test-call + real-call single source.

2026 rule: TELEPHONY-CHEAP — har segment chhota (~10–15 sec). Lambi pitch = zyada
minute = zyada paisa (Vobiz ₹0.45+/min).

Consumers: web_call (test) · vobiz_stream (real) · phone_stream · platform_pitch ·
niche_scripts ai_marketing · telecaller_brain opening_line · latency pre-synth.
"""

def _marketing_start_price() -> str:
    try:
        from app.marketing.packages import get_public_packages

        for pkg in get_public_packages():
            if str(pkg.get("key") or "").strip().lower() == "starter":
                return f"₹{int(pkg.get('price_inr_month') or 0):,}"
    except Exception:
        pass
    return "₹1,999"


UNIVERSAL_AGENT_INTRO = (
    "Namaste! Leads Generation AI se bol rahi hoon — "
    "aapke business ke liye Instagram, Facebook aur Google par demand lane ka kaam AI se. "
    "2026 ka social marketing, agency jaisa kharcha nahi — "
    "business grow karna mera kaam hai, FREE trial dekho, main best solution dhoondungi."
)

PITCH_SHORT = (
    "Social posts, ads aur Google boost — sab AI se automatic, "
    f"{_marketing_start_price()} mahine se, agency se sasta aur simple."
)

INTEREST_ASK = "Agar yeh aapke growth ke kaam ka lage to interested hain — haan ya nahi?"


def platform_opening_segments() -> list[str]:
    """3-part ai_marketing greet — web-call + Vobiz/phone real calls."""
    return [UNIVERSAL_AGENT_INTRO, PITCH_SHORT, INTEREST_ASK]


__all__ = [
    "INTEREST_ASK",
    "PITCH_SHORT",
    "UNIVERSAL_AGENT_INTRO",
    "platform_opening_segments",
]
