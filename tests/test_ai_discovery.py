"""Tests for AI-agent discovery files (/llms.txt + /pricing.md builders).

Builders are pure + offline (no network/LLM) → safe in the targeted suite.
Key guard: pricing.md must reflect the LIVE billing source of truth (packages.py
+ voice_packages.py) so it can never drift from real prices.
"""

from __future__ import annotations

from app.marketing.ai_discovery import build_llms_txt, build_pricing_md


def test_llms_txt_structure():
    txt = build_llms_txt("https://example.com")
    # llmstxt.org spec: H1 title + blockquote summary
    assert txt.startswith("# LeadsGenAI")
    assert "\n> " in txt
    # uses the passed base url (no hardcoded domain leak)
    assert "https://example.com/pricing" in txt
    assert "https://example.com/voice-agent" in txt
    # agent-discovery links present
    assert "/.well-known/agent.json" in txt
    assert "/pricing.md" in txt


def test_llms_txt_never_raises_on_bad_base():
    # empty/None base must still yield a valid file (falls back to default domain)
    assert build_llms_txt("").startswith("# LeadsGenAI")
    assert build_llms_txt(None).startswith("# LeadsGenAI")  # type: ignore[arg-type]


def test_pricing_md_reflects_marketing_source_of_truth():
    from app.marketing.packages import get_public_packages

    md = build_pricing_md("https://example.com")
    assert md.startswith("# Pricing — LeadsGenAI")
    # every PUBLIC marketing plan's monthly price must appear (drift guard)
    for p in get_public_packages():
        price = p.get("price_inr_month")
        if price:
            assert f"₹{int(price):,}" in md, f"marketing price {price} missing from pricing.md"


def test_pricing_md_reflects_voice_source_of_truth():
    from app.marketing.voice_packages import BANDS

    md = build_pricing_md("https://example.com")
    # every voice band monthly price must appear (drift guard)
    for info in BANDS.values():
        price = info.get("price_month")
        assert f"₹{int(price):,}" in md, f"voice band price {price} missing from pricing.md"


def test_pricing_md_includes_topups_and_contact():
    md = build_pricing_md("https://example.com")
    assert "top-up" in md.lower()
    assert "admin@leadsgenai.in" in md
    assert "Last updated:" in md  # freshness signal for AI engines
