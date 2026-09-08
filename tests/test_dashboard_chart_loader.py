"""Chart.js loading contracts for the three dashboard surfaces.

Chart rendering is an enhancement, not a page boot dependency. A CDN outage or
slow browser request must not produce ``ReferenceError: Chart is not defined``
or prevent the surrounding KPI/data cards from rendering.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "customer": ROOT / "frontend" / "customer_dashboard.html",
    "admin": ROOT / "frontend" / "admin_dashboard.html",
    "analytics": ROOT / "frontend" / "analytics.html",
}


def _text(name: str) -> str:
    return PAGES[name].read_text(encoding="utf-8")


def test_every_chart_page_has_local_first_loader_and_remote_fallbacks():
    for name in PAGES:
        html = _text(name)
        assert "window.__chartReady=new Promise" in html, name
        assert '"/design-system/vendor/chart.umd.js"' in html, name
        assert "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js" in html, name
        assert "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.7/chart.umd.min.js" in html, (
            name
        )
        assert "script.onerror=function(){ load(index+1); }" in html, name
        # A parser-blocking direct CDN/vendor tag is the race this contract fixes.
        assert '<script src="/design-system/vendor/chart.umd.js"></script>' not in html


def test_customer_render_waits_for_chart_readiness():
    html = _text("customer")
    start = html.index("function renderCharts(d){")
    body = html[start : start + 1_000]
    assert 'if(typeof Chart==="undefined")' in body
    assert "window.__chartReady.then" in body
    assert "_chartRenderQueued" in body


def test_admin_render_and_revenue_trend_wait_for_chart_readiness():
    html = _text("admin")
    start = html.index("function renderCharts(c){")
    body = html[start : start + 1_200]
    assert 'if(typeof Chart==="undefined")' in body
    assert "window.__chartReady.then" in body
    assert "_adminChartRenderQueued" in body

    trend_start = html.index("async function loadRevenueTrend(){")
    trend_body = html[trend_start : trend_start + 600]
    assert 'if(typeof Chart==="undefined")' in trend_body
    assert "loadRevenueTrend._queued" in trend_body


def test_analytics_data_load_waits_for_chart_readiness():
    html = _text("analytics")
    start = html.index("async function load(){")
    body = html[start : start + 700]
    assert 'if(typeof Chart==="undefined")' in body
    assert "window.__chartReady.then" in body
    assert "load._queued" in body
