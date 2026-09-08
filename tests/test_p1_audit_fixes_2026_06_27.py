"""P1 audit fixes + gap-coverage tests (2026-06-27 evidence-based audit).

Covers the safe fixes landed in the audit + the highest-ROI coverage GAPS the audit found:

1. Public-page smoke (Area #2 — was ZERO coverage): revenue-critical pages must render 200.
   Catches template/route-shadow breakage on the acquisition funnel.
2. Lead capture HTTP (Area #6 — only indirect coverage before): POST /api/public/inquiry
   must accept a valid inquiry (never-lose) and stay ban-safe on the honeypot path.
3. Fix B (app/api/leads.py scrape ToS-safe default): /api/leads/scrape must restrict sources
   to google_maps — it must NOT auto-scrape JustDial/IndiaMart (TRAI/ToS ban risk). Before the
   fix, sources=None defaulted to ["google_maps","indiamart","justdial"].
"""

import pytest

# Revenue-critical public pages (server-rendered HTML; plans load client-side via JS).
PUBLIC_PAGES = ["/", "/pricing", "/start", "/audit", "/compare", "/voice-agent"]


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_public_pages_render_200(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path} returned {r.status_code}"
    assert r.content, f"{path} returned empty body"


def test_lead_capture_inquiry_accepts_valid(client, monkeypatch):
    import app.platform.inquiry_hooks as hooks

    async def _noop_run_after_inquiry(*args, **kwargs):
        return None

    monkeypatch.setattr(hooks, "run_after_inquiry", _noop_run_after_inquiry)

    r = client.post(
        "/api/public/inquiry",
        json={
            "name": "Test Owner",
            "business_name": "Test Biz",  # endpoint requires name + business_name both
            "phone": "9876543210",
            "message": "P1 audit smoke",
            "niche": "salon",
        },
    )
    assert r.status_code == 200, r.text
    # Endpoint is file-first never-lose; just assert a non-empty JSON ack.
    assert r.json()


def test_lead_capture_preserves_utm_source(client, monkeypatch):
    """Audit/landing attribution must survive into the durable inquiry record."""
    import app.api.public_site as ps

    captured: dict = {}

    def _fake_append(rec):
        captured.update(rec)
        return True

    monkeypatch.setattr(ps, "_append_jsonl", _fake_append)
    monkeypatch.setattr(ps, "_save_lead_db", lambda rec: None)
    import app.platform.inquiry_hooks as hooks

    async def _noop_run_after_inquiry(*args, **kwargs):
        return None

    monkeypatch.setattr(hooks, "run_after_inquiry", _noop_run_after_inquiry)

    r = client.post(
        "/api/public/inquiry",
        json={
            "name": "Audit Owner",
            "business_name": "Audit Biz",
            "phone": "9876543210",
            "message": "Audit score lead",
            "utm_source": "Audit",
        },
    )
    assert r.status_code == 200, r.text
    assert captured["utm_source"] == "audit"


def test_homepage_avoids_lucide_runtime():
    """Landing page should not ship a 350KB icon runtime for six feature icons."""
    import pathlib

    html = pathlib.Path("frontend/website/index.html").read_text(encoding="utf-8")
    assert "/design-system/vendor/lucide.min.js" not in html
    assert "data-lucide" not in html


def test_audit_page_uses_bounded_fetches():
    """Lead magnet must not stay forever stuck on slow network/API calls."""
    import pathlib

    html = pathlib.Path("frontend/website/audit.html").read_text(encoding="utf-8")
    assert "function fetchWithTimeout" in html
    assert "fetchWithTimeout('/api/public/audit/questions'" in html
    assert "fetchWithTimeout('/api/public/audit/score'" in html
    assert "fetchWithTimeout('/api/public/inquiry'" in html
    assert "utm_source: 'audit'" in html


def test_design_system_stylesheet_is_bundled():
    """Public pages should not pay serial render-blocking @import RTTs."""
    import pathlib

    css = pathlib.Path("frontend/design-system/styles.css").read_text(encoding="utf-8")
    assert "@import" not in css
    assert "--indigo-600" in css
    assert "font-family: 'Inter'" in css
    assert "./tokens/fonts/inter.woff2" in css


def test_public_inquiry_offloads_sync_persistence_and_hooks():
    """Revenue form must avoid sync file/DB/hook work on the ASGI event loop."""
    import pathlib

    src = pathlib.Path("app/api/public_site.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(_append_jsonl, rec)" in src
    assert "await asyncio.to_thread(_save_lead_db, rec)" in src
    assert "await run_after_inquiry(" in src
    assert "from app.platform.inquiry_hooks import run_after_inquiry" in src


def test_upi_submit_offloads_blocking_store_work():
    """Checkout path should not run JSON-store writes directly on event loop."""
    import pathlib

    upi = pathlib.Path("app/api/upi_payments.py").read_text(encoding="utf-8")
    assert "res = await asyncio.to_thread(" in upi
    assert "upi_payments.submit_payment" in upi


def test_lead_capture_honeypot_stays_ban_safe(client):
    # `website` is a honeypot — a filled value means bot. Must not 5xx (silently dropped, ban-safe).
    r = client.post(
        "/api/public/inquiry",
        json={"name": "Bot", "phone": "9999999999", "website": "http://spam.example"},
    )
    assert r.status_code < 500


def test_scrape_endpoint_is_tos_safe(client, monkeypatch):
    """Fix B: /api/leads/scrape restricts sources to google_maps (no JustDial/IndiaMart auto-scrape)."""
    import app.api.leads as leads_mod

    captured: dict = {}

    async def _fake_scrape(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(leads_mod.scraper, "scrape_leads", _fake_scrape)

    r = client.post(
        "/api/leads/scrape",
        json={"niche": "salon", "cities": ["Mumbai"], "max_leads": 5},
    )
    assert r.status_code == 200, r.text
    # BackgroundTask runs synchronously in Starlette TestClient before the request context exits.
    assert captured.get("sources") == ["google_maps"], f"unsafe sources: {captured.get('sources')}"
    assert "indiamart" not in (captured.get("sources") or [])
    assert "justdial" not in (captured.get("sources") or [])


def test_orphan_signup_delegates_to_canonical(client, monkeypatch):
    """Merge: /api/customer/auth/signup (was a divergent duplicate, zero callers) now
    delegates to the single canonical public_signup. Confirms one implementation, no dup."""
    import app.api.public_site as ps

    called: dict = {}

    async def _fake_public_signup(body, request):
        called["business_name"] = getattr(body, "business_name", None)
        called["plan"] = getattr(body, "plan", None)
        return {"ok": True, "client_id": "c_merged", "access_token": "tkn", "token_type": "bearer"}

    monkeypatch.setattr(ps, "public_signup", _fake_public_signup)

    r = client.post(
        "/api/customer/auth/signup",
        json={
            "business_name": "Merge Co",
            "email": "merge@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "phone": "9000000000",
            "plan": "starter",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("client_id") == "c_merged"
    # Payload was adapted into the canonical public_site.SignupIn and forwarded.
    assert called.get("business_name") == "Merge Co"
    assert called.get("plan") == "starter"


def _stub_signup_side_effects(monkeypatch, cid="c_prov"):
    """Neuter public_signup's file/network side effects so we can assert provisioning only."""
    import app.api.customer_auth as ca
    import app.marketing.clients_store as cs

    monkeypatch.setattr(
        cs, "add_client", lambda **k: {"id": cid, "business_name": k.get("business_name")}
    )
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: {"ok": True})


def test_public_signup_provisions_paid_plan(client, monkeypatch):
    """Audit #7: canonical public_signup must provision the plan (activate_plan +
    reset_usage_period) for a PAID signup — was missing on the live funnel path."""
    import app.billing.usage as usage

    _stub_signup_side_effects(monkeypatch)
    activated: dict = {}
    monkeypatch.setattr(usage, "activate_plan", lambda c, p: activated.update(cid=c, plan=p))
    monkeypatch.setattr(usage, "reset_usage_period", lambda c: activated.update(reset=c))

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Paid Biz",
            "email": "paid@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "advanced",
        },
    )
    assert r.status_code == 200, r.text
    assert activated.get("cid") == "c_prov"
    assert activated.get("plan") == "advanced"
    assert activated.get("reset") == "c_prov"


def test_public_signup_skips_provision_on_trial(client, monkeypatch):
    """Trial (₹0) must NOT activate a paid plan — provisioning is paid-only."""
    import app.billing.usage as usage

    _stub_signup_side_effects(monkeypatch, cid="c_trial")
    activated: dict = {}
    monkeypatch.setattr(usage, "activate_plan", lambda c, p: activated.update(called=True))

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Trial Biz",
            "email": "trial@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "trial",
        },
    )
    assert r.status_code == 200, r.text
    assert "called" not in activated, "trial should not activate a paid plan"


def test_public_signup_captures_business_website(client, monkeypatch):
    """Audit 2026-07-04: the honeypot squatted the `website` field name, so the
    self-serve funnel never captured a real site and AUTO_ONBOARD's website→KB
    seed was dead. business_website must land in clients_store, scheme added."""
    import app.billing.usage as usage
    import app.marketing.clients_store as cs

    _stub_signup_side_effects(monkeypatch, cid="c_site")
    monkeypatch.setattr(usage, "activate_plan", lambda *a, **k: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda c: True)
    saved: dict = {}
    monkeypatch.setattr(cs, "update_client", lambda cid, **kw: saved.update(cid=cid, **kw))

    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Site Biz",
            "email": "site@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "plan": "starter",
            "business_website": "sharmasolar.in",
        },
    )
    assert r.status_code == 200, r.text
    assert saved.get("cid") == "c_site"
    assert saved.get("website") == "https://sharmasolar.in"


def test_public_signup_honeypot_still_rejects(client, monkeypatch):
    """The bot-trap `website` field must keep rejecting — the new REAL field is
    business_website, the honeypot is untouched."""
    _stub_signup_side_effects(monkeypatch)
    r = client.post(
        "/api/public/signup",
        json={
            "business_name": "Bot Biz",
            "email": "bot@example.com",
            "password": "secret123",  # pragma: allowlist secret
            "website": "http://spam.example",
        },
    )
    assert r.status_code == 400
