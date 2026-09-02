"""Revenue-funnel contracts for the public pricing CTA.

Live Chrome found that embedding the full plan JSON inside an inline ``onclick``
attribute breaks as soon as a feature contains an apostrophe.  The browser then
raises ``SyntaxError`` on click and the signup/payment modal never opens.
"""

from pathlib import Path

PRICING_HTML = Path("frontend/pricing.html")
SERVICE_WORKER = Path("frontend/website/sw.js")
SECURITY_MIDDLEWARE = Path("app/middleware/__init__.py")


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


def test_service_worker_never_serves_cached_revenue_pages():
    source = SERVICE_WORKER.read_text(encoding="utf-8")

    assert 'p === "/pricing"' in source
    assert 'p === "/start"' in source
    assert 'fetch(request, { cache: "no-store" })' in source


def test_service_worker_never_serves_cached_dashboard_dependencies():
    source = SERVICE_WORKER.read_text(encoding="utf-8")

    assert 'p.startsWith("/design-system/")' in source
    assert 'const CACHE_NAME = "leadgen-ai-v6"' in source


def test_service_worker_never_serves_cached_conversion_pages():
    source = SERVICE_WORKER.read_text(encoding="utf-8")

    for path in [
        "/",
        "/index.html",
        "/audit",
        "/site-audit",
        "/demo",
        "/pricing",
        "/start",
        "/sw.js",
    ]:
        assert f'p === "{path}"' in source
    assert 'fetch(request, { cache: "no-store" })' in source


def test_security_headers_disable_browser_cache_for_revenue_pages():
    source = SECURITY_MIDDLEWARE.read_text(encoding="utf-8")

    for path in [
        "/",
        "/index.html",
        "/audit",
        "/site-audit",
        "/demo",
        "/pricing",
        "/start",
        "/sw.js",
    ]:
        assert f'"{path}"' in source
    assert 'response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"' in source
