"""P0-2026-07-12 incident regression suite — jiya-makeover mobile dashboard
stuck on "Demo Data" + Setup Wizard / Social Networking Setup permanently
stuck on "Load ho raha hai...".

Root cause (reproduced via jsdom execution replay of the live production
bundle, not guesswork — see progress.md P0 loop entry for the full trace):
  1. The main dashboard fetch (tryLive/loadLiveDashboard) had no bounded
     timeout, unlike the Setup Wizard's fetchSetupJson (which already used
     SETUP_TIMEOUT_MS + AbortController). A hung request left a logged-in
     customer on demo data forever with no error and no way to retry.
  2. A response that passed `res.ok` but didn't match the frontend's shape
     check fell through silently — no boot(), no error, no signal.
  3. boot(live) -> renderAll() -> renderCharts() threw on any single
     malformed chart series (reproduced concretely with a charts payload
     missing `leads_by_city`), which aborted every remaining renderAll
     step *and* every independent post-boot call queued after it
     (team/autopilot/delivery-proof/onboarding-redirect).
  4. The bottom-of-script boot sequence (loadBilling/loadContent/.../
     loadGuidedSetup/loadRouting/sec2faLoad/whLoad) ran as bare top-level
     calls — a synchronous throw in any one of them would have silently
     aborted every call after it, which is the only way Setup Wizard and
     Social Networking Setup could stay on "Load ho raha hai..." forever
     even though fetchSetupJson itself has an 8s AbortController timeout.

Fix: each independent card/loader is now wrapped so one failure can't
cascade, the main dashboard fetch is bounded, and a persistent (non-toast)
error banner + retry control exists for a logged-in customer whose live
data genuinely fails to load. This test suite is a static-HTML guard
(matches the established pattern in test_customer_setup_wizard_frontend.py)
— it doesn't require a live authenticated browser session, but a full
jsdom execution replay (harness2.js referenced in progress.md) was used
to originally reproduce and then verify the fix end-to-end.
"""

from pathlib import Path


def _html():
    with open("frontend/customer_dashboard.html", encoding="utf-8") as f:
        return f.read()


def test_dashboard_fetch_has_bounded_timeout():
    """The main dashboard fetch must abort after a fixed timeout — a hung
    backend request must never leave the customer on Demo Data forever."""
    html = _html()
    assert "const DASHBOARD_TIMEOUT_MS" in html
    idx = html.index("async function loadLiveDashboard")
    end = html.index(
        "loadLiveDashboard();", idx + 50
    )  # the initial page-load invocation, past the function body
    snippet = html[idx:end]
    assert "AbortController" in snippet
    assert "signal:ctl.signal" in snippet
    assert "clearTimeout(timer)" in snippet


def test_live_data_error_banner_exists_and_is_persistent():
    """A logged-in customer whose live data fails to load must see a
    persistent, actionable error state — not just a toast that can be
    missed, and never a silent demo fallback."""
    html = _html()
    assert 'id="liveDataErrorBanner"' in html
    assert 'id="liveDataErrorMsg"' in html
    assert "function _showLiveDataError" in html
    assert "function _hideLiveDataError" in html
    assert "function retryLiveDashboard" in html
    # Banner must be retryable; logout escape lives on the live-load failure path
    # (not necessarily inside the first 700 chars of the banner markup).
    banner_idx = html.index('id="liveDataErrorBanner"')
    banner_snippet = html[banner_idx : banner_idx + 700]
    assert 'onclick="retryLiveDashboard()"' in banner_snippet
    idx = html.index("async function loadLiveDashboard")
    load_snippet = html[idx : idx + 2500]
    assert 'localStorage.removeItem("lgai_token")' in load_snippet
    assert "/app/login" in load_snippet


def test_unexpected_dashboard_shape_is_surfaced_not_silent():
    """res.ok===true but a shape that doesn't match kpis/calls/leads must
    show an explicit error, not silently do nothing (the original bug)."""
    html = _html()
    idx = html.index("async function loadLiveDashboard")
    snippet = html[idx : idx + 3500]
    assert "unexpected dashboard payload shape" in snippet
    assert "_showLiveDataError(" in snippet


def test_expired_or_invalid_token_clears_state_and_redirects():
    """401/403 must never fall back to demo silently — clear the stale
    token and send the customer back to login."""
    html = _html()
    idx = html.index("async function loadLiveDashboard")
    snippet = html[idx : idx + 1200]
    assert "res.status===401||res.status===403" in snippet
    assert 'localStorage.removeItem("lgai_token")' in snippet
    assert "/app/login?reason=expired" in snippet


def test_render_all_steps_are_independently_fault_tolerant():
    """One rendering step throwing (most concretely: renderCharts() on a
    malformed charts payload) must never abort the steps queued after it —
    this is what let a single bad chart series silently skip
    renderOnboarding()'s Setup-Wizard-redirect and pushDataNotifications()."""
    html = _html()
    assert "function _safeRenderStep(name, fn)" in html
    idx = html.index("function renderAll(){")
    snippet = html[idx : idx + 1500]
    for step in (
        "renderKPIs",
        "renderSummary",
        "renderCalls",
        "renderLeads",
        "renderCharts",
        "renderOnboarding",
        "pushDataNotifications",
    ):
        assert f'_safeRenderStep("{step}"' in snippet, f"{step} not fault-isolated in renderAll()"


def test_boot_itself_is_fault_tolerant():
    html = _html()
    idx = html.index("function boot(data){")
    snippet = html[idx : idx + 400]
    assert '_safeRenderStep("setMeta"' in snippet
    assert '_safeRenderStep("initCampaigns"' in snippet


def test_chart_series_are_defensively_normalized():
    """Reproduced crash: `d.charts.leads_by_city` not iterable (TypeError)
    inside renderCharts()/renderSummary() when a series is missing/malformed.
    Every series consumed by chart rendering must be Array.isArray-guarded."""
    html = _html()
    idx = html.index("function renderCharts(d){")
    snippet = html[idx : idx + 1500]
    assert "Array.isArray(cd.calls_per_day)" in snippet
    assert "Array.isArray(cd.leads_by_status)" in snippet
    assert "Array.isArray(cd.leads_by_city)" in snippet

    summary_idx = html.index("function renderSummary(d){")
    summary_snippet = html[summary_idx : summary_idx + 400]
    assert "Array.isArray(d.charts&&d.charts.leads_by_city)" in summary_snippet


def test_draw_chart_is_isolated_per_chart():
    """One bad canvas/dataset must not prevent the other two KPI charts
    from rendering (independent-card-render invariant)."""
    html = _html()
    idx = html.index("function drawChart(id,type,data,opts){")
    snippet = html[idx : idx + 550]
    assert "try{" in snippet and "catch(e)" in snippet


def test_chart_loader_waits_for_primary_or_fallback_before_rendering():
    """A successful CDN HTTP response is not enough: dashboard rendering must
    wait until Chart is defined, try the fallback on load/error failure, and
    never execute a bare `Chart.defaults` while both providers are pending."""
    html = _html()
    head = html[: html.index("</head>")]
    assert "window.__chartReady" in head
    assert "cdn.jsdelivr.net/npm/chart.js" in head
    assert "cdnjs.cloudflare.com/ajax/libs/Chart.js" in head
    assert "onload" in head and "onerror" in head

    idx = html.index("function renderCharts(d){")
    snippet = html[idx : idx + 800]
    assert 'typeof Chart==="undefined"' in snippet
    assert "window.__chartReady.then" in snippet
    assert snippet.index('typeof Chart==="undefined"') < snippet.index("Chart.defaults")
    assert "_chartPendingData=d" in snippet
    assert "const pending=_chartPendingData" in snippet
    assert "renderCharts(pending)" in snippet


def test_chart_runtime_is_vendored_and_local_first_on_all_dashboards():
    """Authenticated dashboards must not depend on third-party CDNs to render."""
    frontend = Path("frontend")
    asset = frontend / "design-system" / "vendor" / "chart.umd.js"
    license_file = frontend / "design-system" / "vendor" / "chart.js-LICENSE.md"
    assert asset.is_file() and asset.stat().st_size > 100_000
    assert license_file.is_file()

    local_src = "/design-system/vendor/chart.umd.js"
    for page in ("customer_dashboard.html", "admin_dashboard.html", "analytics.html"):
        page_html = (frontend / page).read_text(encoding="utf-8")
        assert local_src in page_html, f"{page} is still CDN-only"
        for remote in ("cdn.jsdelivr.net", "cdnjs.cloudflare.com"):
            if remote in page_html:
                assert page_html.index(local_src) < page_html.index(remote)


def test_init_campaigns_defensive_against_non_array_campaigns():
    html = _html()
    idx = html.index("function initCampaigns(){")
    snippet = html[idx : idx + 300]
    assert "Array.isArray(DATA&&DATA.campaigns)" in snippet


def test_bottom_of_script_loaders_are_individually_isolated():
    """The exact mechanism that could leave Setup Wizard / Social Networking
    Setup permanently on "Load ho raha hai...": these were bare top-level
    calls where one throwing synchronously would silently abort every call
    listed after it. Each loader must now run through _safeBoot()."""
    html = _html()
    assert "function _safeBoot(name, fn)" in html
    idx = html.index('_safeBoot("loadBilling", loadBilling);')
    snippet = html[idx : idx + 500]
    for loader in (
        "loadBilling",
        "loadContent",
        "loadWebTools",
        "loadApprovals",
        "loadGuidedSetup",
        "loadRouting",
        "sec2faLoad",
        "whLoad",
    ):
        assert f'_safeBoot("{loader}", {loader});' in snippet, f"{loader} not isolated"


def test_load_live_dashboard_is_named_and_retryable():
    """Was an anonymous IIFE (tryLive) that could only ever run once at page
    load with no way to retry. Must be a named, re-invokable function."""
    html = _html()
    assert "async function loadLiveDashboard()" in html
    assert "loadLiveDashboard();" in html  # initial invocation at page load
    retry_idx = html.index("function retryLiveDashboard")
    retry_snippet = html[retry_idx : retry_idx + 150]
    assert "loadLiveDashboard()" in retry_snippet


def test_ui_build_marker_present_and_sourced_from_health():
    """2026-07-12 continuation: a non-sensitive build identifier must be
    assertable by browser automation so a "newly deployed" claim can be
    proven, not just asserted. Sourced from the already-existing public
    /health endpoint's APP_VERSION (short git SHA, set by the deploy
    pipeline) rather than inventing new deploy-time templating."""
    html = _html()
    assert '<meta name="ui-build" content="loading">' in html
    idx = html.index('fetch("/health")')
    snippet = html[idx : idx + 700]
    assert 'meta[name="ui-build"]' in snippet
    assert 'document.documentElement.setAttribute("data-ui-build"' in snippet
    assert 'console.log("[UI_BUILD]"' in snippet
    assert 'getElementById("uiBuildValue")' in snippet
    # visible, non-sensitive Support-tab line a human can read off a screenshot
    assert 'id="uiBuildValue"' in html
