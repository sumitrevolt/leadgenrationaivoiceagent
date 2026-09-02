"""Startup diagnostics must report capability without exposing secret material."""

import logging
from contextlib import contextmanager

from app import main


@contextmanager
def _capture(logger: logging.Logger, level: int = logging.INFO):
    records: list[str] = []

    class _H(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _H()
    handler.setLevel(level)
    prev = logger.level
    logger.addHandler(handler)
    logger.setLevel(level)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)


def test_startup_banner_never_logs_google_maps_key(monkeypatch):
    synthetic_key = "FAKE_GOOGLE_MAPS_KEY_FOR_TESTS_ONLY_000"  # pragma: allowlist secret
    monkeypatch.setattr(main.settings, "google_maps_api_key", synthetic_key)

    with _capture(main.logger, logging.INFO) as records:
        main._log_startup_banner()
        rendered = "\n".join(records)

    assert "Google Maps: CONFIGURED (prospecting enabled)" in rendered
    assert f"Telephony: {main.settings.default_telephony}" in rendered
    assert "{settings.default_telephony}" not in rendered
    assert synthetic_key not in rendered
    assert synthetic_key[:8] not in rendered
