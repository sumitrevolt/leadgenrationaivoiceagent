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


# LEAN OPENER (2026-06-27): pehle intro ek hi segment me 4-5 ideas thunsta tha
# (~45 shabd, ~20 sec bolne me) — "pitch lambi hai" user-feedback. Ab intro = sirf
# identity + ek hook; price/trial pitch-segment me; ask chhota. Total ~90→~50 shabd
# (telephony-cheap + caller bore na ho). AI-disclosure helper (ensure_ai_disclosure)
# iske aage "Main ek AI assistant hoon." prepend karta — isliye yahan dobara mat likho.
UNIVERSAL_AGENT_INTRO = (
    "Namaste! Main Leads Generation AI se bol rahi hoon — "
    "hum aapke jaise business ko AI se naye customers dilate hain, "
    "Instagram, Facebook aur Google se."
)

PITCH_SHORT = (
    "Aapko khud kuch nahi karna — roz ki posts, ads aur Google par upar aana, "
    f"sab AI automatic karta hai. {_marketing_start_price()} mahine se, agency se kaafi sasta, "
    "aur 7 din bilkul FREE trial."
)

INTEREST_ASK = "Ek baar free me try karke dekhna chahenge?"


def platform_opening_segments() -> list[str]:
    """3-part ai_marketing greet — web-call + Vobiz/phone real calls."""
    return [UNIVERSAL_AGENT_INTRO, PITCH_SHORT, INTEREST_ASK]


__all__ = [
    "INTEREST_ASK",
    "PITCH_SHORT",
    "UNIVERSAL_AGENT_INTRO",
    "platform_opening_segments",
]
