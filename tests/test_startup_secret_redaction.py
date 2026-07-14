"""Startup diagnostics must report capability without exposing secret material."""

import logging

from app import main


def test_startup_banner_never_logs_google_maps_key(monkeypatch, caplog):
    synthetic_key = "AIzaSyD-abc123_ABC456def789ghiJKL012mno"  # nosecret
    monkeypatch.setattr(main.settings, "google_maps_api_key", synthetic_key)

    with caplog.at_level(logging.INFO):
        main._log_startup_banner()

    rendered = caplog.text
    assert "Google Maps: CONFIGURED (prospecting enabled)" in rendered
    assert f"Telephony: {main.settings.default_telephony}" in rendered
    assert "{settings.default_telephony}" not in rendered
    assert synthetic_key not in rendered
    assert synthetic_key[:8] not in rendered
