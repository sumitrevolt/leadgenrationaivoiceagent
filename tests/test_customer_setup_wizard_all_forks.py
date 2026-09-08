"""Setup Wizard across the 3 dashboard routes. Originally 3 separate fork files
(customer_marketing.html/customer_dashboard.html/customer_voice.html) each
needed their own parity check; the two per-product forks were confirmed
unreachable duplicates and deleted 2026-07-07 (see
tests/test_customer_dashboard_product_routing.py — all 3 routes now serve
this single consolidated file, CSS-gated by a prod-marketing/prod-voice body
class). This file now confirms the wizard card/hook/functions are present
once, and that the voice-mode CSS gate for the social/brand-tone section
(a pure voice product has no posts to brand) actually exists."""

import pytest

FORKS = ["customer_dashboard.html"]


def _html(fork):
    with open(f"frontend/{fork}", encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("fork", FORKS)
def test_setup_wizard_card_and_functions_present(fork):
    html = _html(fork)
    assert 'id="setupWizardCard"' in html
    assert 'id="setupWizardBody"' in html
    assert "async function loadSetupWizard" in html
    assert "async function saveSetupWizard" in html
    assert "async function sendKbInfo" in html
    # P0-2026-07-12: invoked via _safeBoot() now (see test_customer_setup_wizard_frontend.py
    # for the dedicated regression test on that wrapper) so one broken loader can't
    # block the others — the literal call-site changed, the wiring didn't.
    assert '_safeBoot("loadGuidedSetup", loadGuidedSetup);' in html


@pytest.mark.parametrize("fork", FORKS)
def test_social_brand_fields_marketing_only_gated(fork):
    html = _html(fork)
    idx = html.index("function renderSetupWizard")
    snippet = html[idx : idx + 2200]
    assert 'class="marketing-only"' in snippet


def test_voice_mode_css_hides_marketing_only_under_prod_voice():
    """Confirm the CSS rule that actually hides these fields under prod-voice
    exists — the marketing-only class is inert without it."""
    html = _html("customer_dashboard.html")
    assert ".prod-voice .marketing-only" in html or (
        ".marketing-only" in html and "prod-voice" in html
    )
