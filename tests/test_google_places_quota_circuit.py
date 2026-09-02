"""Google Places quota circuit-breaker contracts."""

from __future__ import annotations

import asyncio


def _scraper():
    from app.lead_scraper.google_maps import GoogleMapsScraper

    scraper = object.__new__(GoogleMapsScraper)
    scraper.api_key = "test-key"
    return scraper


def test_quota_exhaustion_never_cascades_to_legacy_or_browser(monkeypatch):
    from app.lead_scraper import google_maps
    from app.platform import integration_health

    scraper = _scraper()
    calls: list[str] = []

    async def _quota(*_args):
        raise google_maps.PlacesQuotaExhausted()

    async def _legacy(*_args):
        calls.append("legacy")
        return []

    async def _browser(*_args):
        calls.append("browser")
        return []

    monkeypatch.setattr(integration_health, "places_quota_cooldown_remaining", lambda: 0)
    monkeypatch.setattr(scraper, "_search_with_places_new", _quota)
    monkeypatch.setattr(scraper, "_search_with_api", _legacy)
    monkeypatch.setattr(scraper, "_search_with_scraping", _browser)

    assert asyncio.run(scraper.search_businesses("solar", "Pune")) == []
    assert calls == []


def test_normal_empty_places_response_keeps_legacy_fallback(monkeypatch):
    from app.platform import integration_health

    scraper = _scraper()
    calls: list[str] = []

    async def _empty(*_args):
        return []

    async def _legacy(*_args):
        calls.append("legacy")
        return []

    monkeypatch.setattr(integration_health, "places_quota_cooldown_remaining", lambda: 0)
    monkeypatch.setattr(scraper, "_search_with_places_new", _empty)
    monkeypatch.setattr(scraper, "_search_with_api", _legacy)

    assert asyncio.run(scraper.search_businesses("solar", "Pune")) == []
    assert calls == ["legacy"]


def test_429_records_failure_and_starts_shared_cooldown(monkeypatch):
    import httpx

    from app.lead_scraper import google_maps
    from app.platform import integration_health

    scraper = _scraper()
    recorded: list[str] = []
    cooldowns: list[bool] = []
    successes: list[bool] = []

    class _Response:
        status_code = 429
        text = "quota exhausted"

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: _Client())
    monkeypatch.setattr(
        integration_health, "record_failure", lambda _name, note: recorded.append(note)
    )
    monkeypatch.setattr(
        integration_health, "start_places_quota_cooldown", lambda: cooldowns.append(True)
    )
    monkeypatch.setattr(integration_health, "record_success", lambda _name: successes.append(True))

    try:
        asyncio.run(scraper._search_with_places_new("solar", "Pune", 1))
    except google_maps.PlacesQuotaExhausted:
        pass
    else:
        raise AssertionError("429 must stop fallback processing")

    assert recorded == ["http_429"]
    assert cooldowns == [True]
    assert successes == []


def test_quota_cooldown_helpers_never_raise_when_redis_is_unavailable(monkeypatch):
    from app.platform import integration_health

    monkeypatch.setattr(integration_health, "_redis", lambda: (_ for _ in ()).throw(RuntimeError()))
    integration_health.start_places_quota_cooldown()
    assert integration_health.places_quota_cooldown_remaining() == 0
