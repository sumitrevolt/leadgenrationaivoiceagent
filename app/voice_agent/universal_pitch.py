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


def _voice_start_price() -> str:
    try:
        from app.marketing.voice_packages import BANDS

        price = BANDS.get("A", {}).get("price_month") or 4999
        return f"₹{int(price):,}"
    except Exception:
        pass
    return "₹4,999"


# =========================================================================== #
# PRODUCT 1: AI Marketing Automation (Main Product)
# =========================================================================== #
UNIVERSAL_AGENT_INTRO = (
    "Namaste! Main LeadGen AI se bol rahi hoon. Hum local businesses ko roz "
    "Instagram, Facebook aur Google par active rakhte hain — taki naye customers "
    "roz milein. Do minute baat kar sakti hoon?"
)

PITCH_SHORT = (
    "Aapko kuch nahi karna — AI roz posts, ads aur Google ranking sambhalta hai, "
    f"taaki roz naye customers milein. {_marketing_start_price()} mahine se, agency se kaafi "
    "kam kharcha — aur 7 din FREE trial, bina card ke."
)

INTEREST_ASK = "Ek baar free me try karke dekhna chahenge?"


# =========================================================================== #
# PRODUCT 2: AI Voice Calling Agent (Standalone AI Telecaller)
# =========================================================================== #
VOICE_AGENT_INTRO = (
    "Namaste! Main LeadGen AI se bol rahi hoon. Hum businesses ke liye human-like "
    "AI telecaller provide karte hain jo incoming aur outgoing calls, lead followups "
    "aur appointment booking 24 ghante sambhalta hai. Do minute baat ho sakti hai?"
)

VOICE_AGENT_PITCH_SHORT = (
    "Hamara AI telecaller bilkul insaan ki tarah Hinglish me baat karta hai, ek sath 100+ calls "
    f"handle karta hai aur calendar me appointment book kar deta hai. {_voice_start_price()} mahine se "
    "unlimited calls — traditional telecalling team se 80% sasta, aur 7 din free pilot."
)

VOICE_AGENT_INTEREST_ASK = "Kya aap apne business ke liye AI calling ka free demo dekhna chahenge?"


def platform_opening_segments() -> list[str]:
    """ai_marketing greet — single short opener (wait for caller before pitch)."""
    from app.voice_agent.platform_pitch import opening_segments

    return opening_segments()


__all__ = [
    "INTEREST_ASK",
    "PITCH_SHORT",
    "UNIVERSAL_AGENT_INTRO",
    "VOICE_AGENT_INTEREST_ASK",
    "VOICE_AGENT_INTRO",
    "VOICE_AGENT_PITCH_SHORT",
    "platform_opening_segments",
]

