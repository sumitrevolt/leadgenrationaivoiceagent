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
    "Namaste! Leads Generation AI se bol rahi hoon — "
    "aapke business ke liye Instagram, Facebook aur Google par AI se naye customers."
)

PITCH_SHORT = (
    "Sab automatic — roz ke posts, ads aur Google boost; "
    f"{_marketing_start_price()} mahine se, agency se sasta. 7 din FREE trial bhi."
)

INTEREST_ASK = "Aapke growth ke kaam ka lage to — interested hain?"


def platform_opening_segments() -> list[str]:
    """3-part ai_marketing greet — web-call + Vobiz/phone real calls."""
    return [UNIVERSAL_AGENT_INTRO, PITCH_SHORT, INTEREST_ASK]


__all__ = [
    "INTEREST_ASK",
    "PITCH_SHORT",
    "UNIVERSAL_AGENT_INTRO",
    "platform_opening_segments",
]
