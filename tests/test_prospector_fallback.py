"""Rohan prospector reliability contracts."""

from __future__ import annotations

import asyncio
import threading


def test_google_empty_response_falls_back_to_osm_off_loop(monkeypatch, tmp_path):
    from app.lead_scraper import google_maps
    from app.platform import prospector, team

    class _EmptyGoogle:
        api_key = "test-key"  # pragma: allowlist secret

        async def search_businesses(self, **_kwargs):
            return []

    osm_threads: list[str] = []
    stored: list[dict] = []

    def _osm(_query, _city, _limit):
        osm_threads.append(threading.current_thread().name)
        return [
            {
                "business_name": "Pune Solar Works",
                "phone": "+919876543210",
                "address": "Pune",
                "website": "",
            }
        ]

    monkeypatch.setattr(google_maps, "GoogleMapsScraper", _EmptyGoogle)
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "prospects.jsonl"))
    monkeypatch.setattr(prospector, "_read_all", lambda: [])
    monkeypatch.setattr(
        prospector,
        "_targets",
        lambda: [{"niche": "solar_residential", "query": "solar installer", "cities": ["Pune"]}],
    )
    monkeypatch.setattr(prospector, "_osm_search", _osm)
    monkeypatch.setattr(prospector, "_append", lambda row: stored.append(row) or True)
    monkeypatch.setattr(prospector, "_phone_type", lambda _phone: "mobile")
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)

    result = asyncio.run(prospector.run_prospecting(limit_per_query=1))

    assert result["new"] == 1
    assert result["queries_empty"] == 0
    assert result["scraper"] == "google_maps_api+osm_fallback"
    assert stored[0]["business_name"] == "Pune Solar Works"
    assert osm_threads and all(name != "MainThread" for name in osm_threads)


def test_historical_official_or_helpline_record_is_not_quality_approved():
    from app.platform import prospector

    assert not prospector.is_quality_approved(
        {
            "business_name": "IRCTC Customer Care Helpline",
            "phone": "+911234567890",
            "status": "ready",
            "source_query": "solar installer",
        }
    )


def test_query_budget_caps_slow_provider_fallback_chain(monkeypatch, tmp_path):
    """Daily prospecting must stay below the heavy-worker task deadline."""
    from app.platform import prospector, team

    calls: list[tuple[str, str]] = []

    def _osm(query, city, _limit):
        calls.append((query, city))
        return []

    async def _no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setenv("PROSPECT_MAX_QUERIES", "2")
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "prospects.jsonl"))
    monkeypatch.setattr(prospector, "_read_all", lambda: [])
    monkeypatch.setattr(
        prospector,
        "_targets",
        lambda: [
            {
                "niche": "solar_residential",
                "query": "solar installer",
                "cities": ["Pune", "Mumbai", "Nagpur"],
            }
        ],
    )
    monkeypatch.setattr(prospector, "_osm_search", _osm)
    monkeypatch.setattr(prospector.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(team, "log_event", lambda *args, **kwargs: None)

    result = asyncio.run(prospector.run_prospecting(limit_per_query=1))

    assert result["queries_run"] == 2
    assert result["queries_capped"] is True
    assert calls == [("solar installer", "Pune"), ("solar installer", "Mumbai")]
