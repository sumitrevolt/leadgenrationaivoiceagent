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
# Permission-opener (2026-07-02): self-test ne har platform-opener pe
# MISSING_PERMISSION flag kiya — intro kabhi "do minute hai?" nahi poochta tha.
# Gong-research: permission/timing ask se cold-call ~5-10x behtar convert hoti +
# caller ko control deta (kam pushy). Ek chhota timing-ask turn-1 me add — segment
# lean rehta (telephony-cheap), qa_checks.has_permission_ask ab pass karta.
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


def platform_opening_segments() -> list[str]:
    """ai_marketing greet — single short opener (wait for caller before pitch)."""
    from app.voice_agent.platform_pitch import opening_segments

    return opening_segments()


__all__ = [
    "INTEREST_ASK",
    "PITCH_SHORT",
    "UNIVERSAL_AGENT_INTRO",
    "platform_opening_segments",
]
