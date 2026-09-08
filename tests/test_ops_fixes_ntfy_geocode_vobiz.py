"""Live-prod triage fixes (2026-07-06 VPS audit).

1. ntfy: emoji-titles ascii-strip ke baad LEADING SPACE bachta tha ("⏭ Boot-grace
   skip" → " Boot-grace skip") → httpx "Illegal header value" → founder ko alert
   deliver hi nahi hota tha. Header-safe sanitize (collapse whitespace + strip).
2. google_maps geocode: bare city ("Thane"/"Aurangabad" — ambiguous across states)
   par ZERO_RESULTS → poori city ke prospects skip. ", India" bias retry.
3. vobiz get_balance/place_call: blank `str(e)` ("failed: ") se root-cause
   undiagnosable — exception TYPE bhi log/return me chahiye.
"""

from __future__ import annotations

import asyncio

import httpx

from app.integrations import ntfy


class _FakeResp:
    status_code = 200

    def json(self):
        return {}


class _CaptureClient:
    captured: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, content=None, json=None, headers=None, **k):
        _CaptureClient.captured = {"url": url, "headers": headers or {}, "json": json}
        return _FakeResp()


def test_ntfy_title_header_sanitized(monkeypatch):
    monkeypatch.setenv("NTFY_URL", "http://ntfy:80")
    monkeypatch.setenv("NTFY_TOPIC", "alerts")
    monkeypatch.setattr(httpx, "AsyncClient", _CaptureClient)
    ok = asyncio.run(ntfy.push("⏭ Boot-grace skip: evening_prospect", "hello"))
    assert ok is True
    title = _CaptureClient.captured["headers"]["Title"]
    assert title == "Boot-grace skip: evening_prospect", (
        f"leading/trailing whitespace must be stripped from the Title header, got {title!r}"
    )


def test_ntfy_title_newlines_collapsed(monkeypatch):
    monkeypatch.setenv("NTFY_URL", "http://ntfy:80")
    monkeypatch.setenv("NTFY_TOPIC", "alerts")
    monkeypatch.setattr(httpx, "AsyncClient", _CaptureClient)
    asyncio.run(ntfy.push("line1\nline2\r\n  line3", "msg"))
    assert _CaptureClient.captured["headers"]["Title"] == "line1 line2 line3"


def test_geocode_retries_with_india_bias(monkeypatch):
    from app.lead_scraper.google_maps import GoogleMapsScraper

    calls: list[str] = []

    class _GeoResp:
        status_code = 200

        def __init__(self, payload):
            self._p = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._p

    class _GeoClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, **k):
            addr = (params or {}).get("address", "")
            calls.append(addr)
            if "india" in addr.lower():
                return _GeoResp(
                    {
                        "status": "OK",
                        "results": [{"geometry": {"location": {"lat": 19.2, "lng": 72.97}}}],
                    }
                )
            return _GeoResp({"status": "ZERO_RESULTS", "results": []})

    import app.lead_scraper.google_maps as gm

    monkeypatch.setattr(gm.httpx, "AsyncClient", _GeoClient)
    scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
    scraper.api_key = "test-key"
    coords = asyncio.run(scraper._geocode_location("Thane"))
    assert coords == {"lat": 19.2, "lng": 72.97}, "must retry with ', India' bias"
    assert calls == ["Thane", "Thane, India"]


def test_vobiz_error_includes_exception_type(monkeypatch):
    from app.telephony.vobiz_handler import VobizClient

    class _BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectTimeout("")  # blank str(e) — the live symptom

    monkeypatch.setattr(httpx, "AsyncClient", _BoomClient)
    client = VobizClient.__new__(VobizClient)
    client.base_url = "https://api.vobiz.example/v1/acct"
    monkeypatch.setattr(client, "_headers", lambda: {}, raising=False)
    res = asyncio.run(client.get_balance())
    assert res["status_code"] == 0
    assert "ConnectTimeout" in str(res["body"].get("error", "")), (
        "blank str(e) must still surface the exception TYPE for triage"
    )
