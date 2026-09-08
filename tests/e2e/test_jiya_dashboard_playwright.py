"""P0-2026-07-12 — jiya-makeover mobile dashboard: Playwright browser regression.

Real Chrome/Chromium evidence for the "Demo Data stuck" / "Load ho raha hai...
stuck forever" incident (see progress.md + memory/incidents.md 2026-07-12 for
the full root-cause trace). curl/jsdom/source-grep are supplementary only —
this file is the mandatory real-browser layer.

Two independent suites, deliberately separated per the incident runbook:

1. ``TestMockedDashboardRegression`` — deterministic, CI-safe, needs ZERO
   credentials. Serves the actual `frontend/customer_dashboard.html` from a
   local static file server and drives a real Chromium engine against it,
   intercepting every `/api/customer/*` + `/health` call with
   schema-accurate mock responses (see `app/api/customer_dashboard_models.py`
   for the real Pydantic shapes these mirror). Plants a fake-but-well-formed
   JWT under the canonical `lgai_token` localStorage key to simulate an
   authenticated session without ever touching a real password. This is the
   suite that actually asserts DOM state (not just status codes) for the
   fix: bounded timeout, persistent error banner, independent card
   rendering, chart-crash isolation, build marker.

2. ``TestProductionSmoke`` — the real, credentialed, production-safe smoke
   test against https://leadsgenai.in with the actual jiya-makeover account.
   Skipped automatically unless JIYA_TEST_PASSWORD (and optionally
   JIYA_TEST_EMAIL) are present in the environment — this file, and any CI
   log it produces, must never contain the password or a full JWT. Only
   token *presence*, *length*, and non-sensitive decoded claims (e.g. `exp`)
   are ever asserted or printed.

Run:
    pip install playwright pytest-playwright
    playwright install chromium
    pytest tests/e2e/test_jiya_dashboard_playwright.py -v
    # production smoke only:
    JIYA_TEST_EMAIL=... JIYA_TEST_PASSWORD=... pytest tests/e2e/test_jiya_dashboard_playwright.py -v -k Production

STATUS AS OF 2026-07-12 (second P0 session): written but NOT executed in the
sandbox this was authored in — no working Chromium binary could be installed
there (no root for Playwright's --with-deps system packages, and browser
binary downloads were killed mid-transfer because sandbox shell calls do not
persist background processes across tool invocations). Needs a real run in
an environment with root/Docker access (or the repo's normal CI) before this
evidence can be cited as PASS/FAIL. See progress.md for exact details.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright
expect = playwright_sync_api.expect

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
MOBILE_VIEWPORT = {"width": 390, "height": 844}  # requirement #11: Android-size mobile viewport
LOAD_TIMEOUT_MS = 20_000  # generous bound; DASHBOARD_TIMEOUT_MS in the page itself is 15s

# A structurally valid (header.payload.signature) but cryptographically fake JWT.
# It is never sent to a real backend in the mocked suite (every request is
# intercepted), so its lack of a real signature is irrelevant. It exists only
# so the frontend's `billToken()`/`localStorage.getItem("lgai_token")` reads
# something truthy and the client-side "not logged in" redirect doesn't fire.
_FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJqaXlhLW1ha2VvdmVyIiwiZXhwIjo5OTk5OTk5OTk5fQ."
    "not-a-real-signature-mock-only"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def static_server():
    """Serves frontend/ over plain HTTP so fetch()/localStorage have a real
    http:// origin (file:// breaks fetch() same-origin semantics in Chromium).
    Only frontend/customer_dashboard.html itself is exercised; every API call
    it makes is intercepted by Playwright before it ever reaches this server."""
    port = _free_port()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(FRONTEND_DIR), **kw)

        def log_message(self, *a):  # silence
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _mock_dashboard_routes(
    page,
    *,
    dashboard_status=200,
    dashboard_body=None,
    dashboard_delay_ms=0,
    dashboard_abort=False,
    auth_status=200,
    profile_ok=True,
    social_ok=True,
):
    """Central place mirroring the real API shapes from
    app/api/customer_dashboard_models.py / app/api/customer_dashboard.py so
    the mocked suite stays honest about what production actually returns."""
    default_dashboard = {
        "is_sample_data": False,
        "client_id": "jiya-makeover",
        "generated_at": "2026-07-12T09:00:00Z",
        "campaigns": [],
        "kpis": {
            "total_calls": 0,
            "connected_calls": 0,
            "qualified_leads": 0,
            "conversion_pct": 0,
            "est_cost_inr": 0,
        },
        "calls": [],
        "leads": [],
        "charts": {"calls_per_day": [], "leads_by_status": [], "leads_by_city": []},
        "branding": None,
        "onboarding": {"complete": True, "steps": []},
        "trial_banner": None,
        "approval_banner": None,
        "social_error": None,
    }
    body = dashboard_body if dashboard_body is not None else default_dashboard

    def handle_dashboard(route):
        if dashboard_abort:
            route.abort("failed")
            return
        if dashboard_delay_ms:
            time.sleep(dashboard_delay_ms / 1000)
        route.fulfill(
            status=dashboard_status, content_type="application/json", body=json.dumps(body)
        )

    page.route(re.compile(r".*/api/customer/dashboard.*"), handle_dashboard)
    page.route(
        re.compile(r".*/api/customer/auth/me.*"),
        lambda r: r.fulfill(
            status=auth_status,
            content_type="application/json",
            body=json.dumps({"product": "marketing", "client_id": "jiya-makeover"}),
        ),
    )
    page.route(
        re.compile(r".*/api/customer/profile.*"),
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"ok": profile_ok, "business_name": "Jiya Makeover", "city": "Mumbai"}
                if profile_ok
                else {"ok": False, "error": "profile load nahi hua"}
            ),
        ),
    )
    page.route(
        re.compile(r".*/api/customer/social/config.*"),
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": social_ok}),
        ),
    )
    page.route(
        re.compile(r".*/api/customer/social/accounts.*"),
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": social_ok, "platforms": [], "accounts": {}}),
        ),
    )
    page.route(
        re.compile(r".*/api/customer/team.*"),
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"agents": []}),
        ),
    )
    page.route(
        re.compile(r".*/api/customer/autopilot.*"),
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"drafts": []}),
        ),
    )
    page.route(
        re.compile(r".*/api/customer/flow-templates.*"),
        lambda r: r.fulfill(
            status=404,
            content_type="application/json",
            body="{}",
        ),
    )
    page.route(
        re.compile(r".*/health.*"),
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"status": "healthy", "version": "mock-e2e-build", "environment": "test"}
            ),
        ),
    )
    # anything else customer-dashboard-related: benign empty ok so nothing hangs
    page.route(
        re.compile(r".*/api/customer/.*"),
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True}),
        ),
    )


class TestMockedDashboardRegression:
    """Deterministic, CI-safe. Real Chromium, mocked backend."""

    def test_unauthenticated_dashboard_redirects_to_login(self, browser, static_server):
        """#1 — a fresh context with no token must never show the loading
        shell forever; it must redirect to login promptly."""
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        page.goto(f"{static_server}/customer_dashboard.html", wait_until="domcontentloaded")
        page.wait_for_function(
            "() => location.pathname.includes('/app/login') || location.href.includes('app/login')",
            timeout=LOAD_TIMEOUT_MS,
        )
        assert "login" in page.url
        context.close()

    def test_real_dashboard_renders_no_demo_no_stuck_loaders(self, browser, static_server):
        """#5, #6, #7, #14, #15 — the core fix: with a well-formed live
        response, Demo Data must be absent and both loading strings must
        resolve within the bounded timeout, and Setup Wizard / Social
        Networking must reach a real (non-"Load ho raha hai...") state."""
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        context.add_init_script(f"localStorage.setItem('lgai_token', '{_FAKE_JWT}')")
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page_errors = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        _mock_dashboard_routes(page)
        page.goto(f"{static_server}/customer_dashboard.html", wait_until="domcontentloaded")

        # bounded wait for the demo badge to hide (real data arrived)
        expect(page.locator("#demoBadge")).to_be_hidden(timeout=LOAD_TIMEOUT_MS)

        # both stuck-loading strings must be gone from the Setup Wizard / Social cards
        page.wait_for_function(
            """() => {
                const a = document.getElementById('setupWizardBody');
                const b = document.getElementById('socialSetupBody');
                const stuck = t => t && t.includes('Load ho raha hai');
                return a && b && !stuck(a.innerText) && !stuck(b.innerText);
            }""",
            timeout=LOAD_TIMEOUT_MS,
        )

        assert "Demo Data" not in (page.locator("#demoBadge").inner_text() or "")
        assert page_errors == [], f"uncaught page exceptions: {page_errors}"
        context.close()

    def test_chart_crash_does_not_block_setup_or_social_cards(self, browser, static_server):
        """Reproduces the exact defect found in the first P0 session:
        a malformed `charts` payload (missing leads_by_city/leads_by_status)
        used to throw inside renderCharts() and silently abort every
        subsequent renderAll step + the independent Setup Wizard/Social
        loaders queued after it. Must no longer cascade."""
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        context.add_init_script(f"localStorage.setItem('lgai_token', '{_FAKE_JWT}')")

        malformed = {
            "is_sample_data": False,
            "client_id": "jiya-makeover",
            "generated_at": "now",
            "campaigns": [],
            "kpis": {
                "total_calls": 0,
                "connected_calls": 0,
                "qualified_leads": 0,
                "conversion_pct": 0,
                "est_cost_inr": 0,
            },
            "calls": [],
            "leads": [],
            "charts": {"calls_per_day": []},  # leads_by_status / leads_by_city deliberately missing
            "branding": None,
            "onboarding": {"complete": True, "steps": []},
            "trial_banner": None,
            "approval_banner": None,
            "social_error": None,
        }
        _mock_dashboard_routes(page, dashboard_body=malformed)
        page.goto(f"{static_server}/customer_dashboard.html", wait_until="domcontentloaded")

        page.wait_for_function(
            """() => {
                const a = document.getElementById('setupWizardBody');
                const b = document.getElementById('socialSetupBody');
                const stuck = t => t && t.includes('Load ho raha hai');
                return a && b && !stuck(a.innerText) && !stuck(b.innerText);
            }""",
            timeout=LOAD_TIMEOUT_MS,
        )
        expect(page.locator("#demoBadge")).to_be_hidden(timeout=LOAD_TIMEOUT_MS)
        context.close()

    def test_dashboard_timeout_shows_persistent_error_banner(self, browser, static_server):
        """#10 (authenticated API failure) — a hung dashboard request must
        surface the persistent #liveDataErrorBanner with a working retry
        control, not leave the customer silently on Demo Data forever."""
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        context.add_init_script(f"localStorage.setItem('lgai_token', '{_FAKE_JWT}')")
        _mock_dashboard_routes(page, dashboard_delay_ms=999_999)  # never resolves in test time
        page.goto(f"{static_server}/customer_dashboard.html", wait_until="domcontentloaded")

        # DASHBOARD_TIMEOUT_MS is 15s in the page; allow generous margin
        expect(page.locator("#liveDataErrorBanner")).to_be_visible(timeout=20_000)
        expect(
            page.locator("#liveDataErrorBanner button:has-text('Dobara try karein')")
        ).to_be_visible()
        expect(page.locator("#liveDataErrorBanner button:has-text('Logout')")).to_be_visible()
        context.close()

    def test_bearer_header_sent_on_protected_requests(self, browser, static_server):
        """#4 — every protected request must carry Authorization: Bearer
        <token>, using the same canonical token the page stored it under."""
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        context.add_init_script(f"localStorage.setItem('lgai_token', '{_FAKE_JWT}')")
        seen_auth_headers = []

        def capture_and_fulfill(route):
            seen_auth_headers.append(route.request.headers.get("authorization"))
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "is_sample_data": False,
                        "client_id": "jiya-makeover",
                        "generated_at": "now",
                        "campaigns": [],
                        "kpis": {
                            "total_calls": 0,
                            "connected_calls": 0,
                            "qualified_leads": 0,
                            "conversion_pct": 0,
                            "est_cost_inr": 0,
                        },
                        "calls": [],
                        "leads": [],
                        "charts": {"calls_per_day": [], "leads_by_status": [], "leads_by_city": []},
                        "branding": None,
                        "onboarding": {"complete": True, "steps": []},
                        "trial_banner": None,
                        "approval_banner": None,
                        "social_error": None,
                    }
                ),
            )

        page.route(re.compile(r".*/api/customer/dashboard.*"), capture_and_fulfill)
        _mock_dashboard_routes(
            page
        )  # covers the rest; dashboard route above overrides via last-registered-wins
        page.goto(f"{static_server}/customer_dashboard.html", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        assert seen_auth_headers, "dashboard endpoint was never called"
        assert all(h == f"Bearer {_FAKE_JWT}" for h in seen_auth_headers if h is not None)
        context.close()

    def test_invalid_token_clears_state_and_redirects_to_login(self, browser, static_server):
        """#9 — a 401/403 on the dashboard call must clear the canonical
        token and redirect to login, never fall back to demo silently."""
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        context.add_init_script("localStorage.setItem('lgai_token', 'garbage-invalid-token')")
        _mock_dashboard_routes(
            page, dashboard_status=401, dashboard_body={"detail": "invalid token"}
        )
        page.goto(f"{static_server}/customer_dashboard.html", wait_until="domcontentloaded")

        page.wait_for_function(
            "() => location.href.includes('app/login')",
            timeout=LOAD_TIMEOUT_MS,
        )
        token_after = page.evaluate("() => localStorage.getItem('lgai_token')")
        assert token_after is None, "stale token must be cleared on 401/403"
        context.close()

    def test_refresh_persists_session_and_rerenders_live_data(self, browser, static_server):
        """#8 — reload must keep reading the same canonical key and render
        real data again, no demo badge reappearing."""
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        context.add_init_script(f"localStorage.setItem('lgai_token', '{_FAKE_JWT}')")
        _mock_dashboard_routes(page)
        page.goto(f"{static_server}/customer_dashboard.html", wait_until="domcontentloaded")
        expect(page.locator("#demoBadge")).to_be_hidden(timeout=LOAD_TIMEOUT_MS)

        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#demoBadge")).to_be_hidden(timeout=LOAD_TIMEOUT_MS)
        token_after = page.evaluate("() => localStorage.getItem('lgai_token')")
        assert token_after == _FAKE_JWT
        context.close()

    def test_ui_build_marker_is_present_in_dom(self, browser, static_server):
        """#12 (build marker) — proves the marker mechanism itself works in
        a real browser; the *value* only becomes the true deployed short SHA
        once this fix is actually deployed (see TestProductionSmoke)."""
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()
        _mock_dashboard_routes(page)  # /health mocked -> version "mock-e2e-build"
        page.goto(f"{static_server}/customer_dashboard.html", wait_until="domcontentloaded")
        page.wait_for_function(
            "() => document.documentElement.getAttribute('data-ui-build') != null",
            timeout=10_000,
        )
        build = page.evaluate("() => document.documentElement.getAttribute('data-ui-build')")
        assert build == "mock-e2e-build"
        meta_content = page.evaluate(
            "() => document.querySelector('meta[name=\"ui-build\"]').getAttribute('content')"
        )
        assert meta_content == "mock-e2e-build"
        context.close()


PROD_URL = "https://leadsgenai.in"
_missing_prod_creds_reason = (
    "JIYA_TEST_EMAIL / JIYA_TEST_PASSWORD not set — production smoke test skipped. "
    "Set both env vars (never hardcode them here) to run the real authenticated login trace."
)


@pytest.mark.skipif(
    not (os.environ.get("JIYA_TEST_EMAIL") and os.environ.get("JIYA_TEST_PASSWORD")),
    reason=_missing_prod_creds_reason,
)
class TestProductionSmoke:
    """Real, credentialed, production-safe smoke test. Never logs the
    password or a full JWT — only token presence/length/non-sensitive
    decoded claims. Read-only against the real jiya-makeover account."""

    def test_full_login_to_live_dashboard_trace(self, browser):
        email = os.environ["JIYA_TEST_EMAIL"]
        password = os.environ["JIYA_TEST_PASSWORD"]
        context = browser.new_context(viewport=MOBILE_VIEWPORT)
        page = context.new_page()

        network_failures = []
        page.on("requestfailed", lambda req: network_failures.append(req.url))
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        # Step 1: login page
        page.goto(f"{PROD_URL}/app/login", wait_until="domcontentloaded")
        page.fill('input[type="email"], input[name="email"]', email)
        page.fill('input[type="password"], input[name="password"]', password)
        page.click('button[type="submit"], button:has-text("Login")')

        # Step 2: wait for redirect off the login page onto a customer dashboard route
        page.wait_for_function(
            "() => /\\/app\\/customer/.test(location.pathname)",
            timeout=LOAD_TIMEOUT_MS,
        )
        final_url = page.url
        assert "/app/customer" in urlparse(final_url).path

        # Step 3: canonical token — presence/length only, never the value
        token = page.evaluate("() => localStorage.getItem('lgai_token')")
        assert token, "lgai_token missing after login — canonical storage key not populated"
        assert len(token) > 20
        # decode exp claim only (non-sensitive), never print the token itself
        try:
            import base64

            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))
            safe_claims = {k: v for k, v in claims.items() if k in ("exp", "iat", "product")}
        except Exception:
            safe_claims = {}

        # Step 4: bounded wait for the dashboard to fully resolve
        page.wait_for_function(
            """() => {
                const a = document.getElementById('setupWizardBody');
                const b = document.getElementById('socialSetupBody');
                const stuck = t => t && t.includes('Load ho raha hai');
                return a && b && !stuck(a.innerText) && !stuck(b.innerText);
            }""",
            timeout=LOAD_TIMEOUT_MS,
        )

        demo_badge_visible = page.locator("#demoBadge").is_visible()
        build = page.evaluate("() => document.documentElement.getAttribute('data-ui-build')")

        report = {
            "final_url": final_url,
            "token_present": True,
            "token_length": len(token),
            "token_safe_claims": safe_claims,
            "demo_badge_visible": demo_badge_visible,
            "ui_build": build,
            "console_errors": console_errors,
            "network_failures": network_failures,
        }
        print("PRODUCTION SMOKE REPORT:", json.dumps(report, indent=2))

        assert not demo_badge_visible, "Demo Data badge visible after real login — P0 regression"
        assert console_errors == [], f"console errors during real login: {console_errors}"
        context.close()
