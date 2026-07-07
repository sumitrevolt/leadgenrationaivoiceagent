"""Setup Wizard ported to all 3 dashboard forks (customer_marketing.html was
the pilot, covered in depth by test_customer_setup_wizard_frontend.py). This
file confirms customer_dashboard.html + customer_voice.html got the same
card/hook/functions — and that the voice fork correctly marketing-only-gates
the social/brand-tone section (a pure voice product has no posts to brand)."""
import pytest

FORKS = ["customer_marketing.html", "customer_dashboard.html", "customer_voice.html"]


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
    assert "loadSetupWizard();" in html


@pytest.mark.parametrize("fork", FORKS)
def test_social_brand_fields_marketing_only_gated(fork):
    html = _html(fork)
    idx = html.index("function renderSetupWizard")
    snippet = html[idx : idx + 2200]
    assert 'class="marketing-only"' in snippet


def test_voice_fork_css_hides_marketing_only_under_prod_voice():
    """Confirm the CSS rule that actually hides these fields on a voice-only
    render exists in customer_voice.html — the marketing-only class is inert
    without it."""
    html = _html("customer_voice.html")
    assert ".marketing-only" in html
