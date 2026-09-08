"""Product-truth lock — public Advanced is Marketing + callback FEATURE, not bundle USP."""

from __future__ import annotations


def test_public_advanced_name_is_not_bundle_usp():
    """Public Advanced must NOT sell 'two products bundled'.

    Advanced = Marketing Product-1 with AI inquiry-callback FEATURE.
    Standalone Voice = Product-2 (voice_packages / /voice-agent).
    """
    from app.marketing.packages import get_public_packages

    advanced = next(p for p in get_public_packages() if p["key"] == "advanced")
    name = str(advanced.get("name") or "")
    badge = str(advanced.get("badge") or "")
    blob = f"{name} {badge} {advanced.get('tagline') or ''}".lower()
    assert "combo" not in blob
    assert "marketing + ai voice" not in blob
    assert float(advanced["price_inr_month"]) == 5999.0
    assert name == "Advanced Marketing"
    assert badge.upper() == "ADVANCED"
