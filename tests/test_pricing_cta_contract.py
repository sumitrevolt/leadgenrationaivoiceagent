"""Revenue-funnel contracts for the public pricing CTA.

Live Chrome found that embedding the full plan JSON inside an inline ``onclick``
attribute breaks as soon as a feature contains an apostrophe.  The browser then
raises ``SyntaxError`` on click and the signup/payment modal never opens.
"""

from pathlib import Path


PRICING_HTML = Path("frontend/pricing.html")


def _source() -> str:
    return PRICING_HTML.read_text(encoding="utf-8")


def test_pricing_cta_never_embeds_plan_json_in_inline_handler():
    source = _source()

    assert "JSON.stringify(JSON.stringify(p))" not in source
    assert 'onclick="openModalByIndex(${i})"' in source


def test_pricing_cta_resolves_plan_from_loaded_catalogue():
    source = _source()

    assert "function openModalByIndex(index)" in source
    assert "const plan = PLANS[Number(index)]" in source
    assert "openModal(plan)" in source
    assert "function openModal(plan)" in source
    assert "SELECTED = plan" in source
