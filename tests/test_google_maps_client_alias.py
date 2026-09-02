"""UDYAM pipeline imports GoogleMapsClient — must resolve to GoogleMapsScraper."""

from __future__ import annotations


def test_google_maps_client_alias_exists():
    from app.lead_scraper.google_maps import GoogleMapsClient, GoogleMapsScraper

    assert GoogleMapsClient is GoogleMapsScraper
