"""Customer dashboard mobile setup discovery and resilient-loader contracts."""

from pathlib import Path


HTML = Path("frontend/customer_dashboard.html")


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def test_mobile_nav_exposes_setup_and_direct_view_actions():
    html = _html()
    start = html.index('<nav class="mobile-app-nav"')
    end = html.index("</nav>", start)
    nav = html[start:end]
    assert [
        nav.index(label) for label in (">Home<", ">Setup<", ">Posts<", ">Leads<", ">Plan<")
    ] == sorted(nav.index(label) for label in (">Home<", ">Setup<", ">Posts<", ">Leads<", ">Plan<"))
    assert "openSetupWizard()" in nav
    assert "showView('home')" in nav


def test_mobile_vague_fab_is_removed():
    html = _html()
    assert 'class="mobile-fab"' not in html


def test_guided_setup_has_four_steps_and_progress():
    html = _html()
    for marker in (
        'id="setupProgressCard"',
        'data-setup-step="1"',
        'data-setup-step="2"',
        'data-setup-step="3"',
        'data-setup-step="4"',
        "Business",
        "Brand",
        "Social",
        "Review",
        "setupCompletion",
        "showSetupStep",
    ):
        assert marker in html


def test_setup_fetch_is_bounded_and_error_is_retryable():
    html = _html()
    assert "AbortController" in html
    assert "SETUP_TIMEOUT_MS" in html
    assert "Dobara try karein" in html
    assert "loadGuidedSetup" in html
    assert "Login ke baad social setup khulega" in html


def test_advanced_social_connection_is_collapsed():
    html = _html()
    assert '<details class="setup-advanced"' in html
    assert "Advanced account connection" in html


def test_demo_badge_starts_hidden_and_is_data_driven():
    html = _html()
    assert (
        'id="demoBadge"' in html
        and 'style="display:none"'
        in html[html.index('id="demoBadge"') - 120 : html.index('id="demoBadge"') + 160]
    )
    assert "d.is_sample_data === true" in html


def test_dark_mode_keeps_mobile_greeting_readable():
    assert "body.dark .hi h1{color:#f8fafc !important}" in _html()
