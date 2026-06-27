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


def test_lead_capture_inquiry_accepts_valid(client):
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
