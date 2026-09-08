"""Delivery logs must prove outcomes without retaining recipient PII."""

from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest

from app.integrations import email_sender as module


def _sender() -> module.EmailSender:
    sender = module.EmailSender.__new__(module.EmailSender)
    sender.host = "smtp.example"
    sender.port = 465
    sender.user = "service-user"
    sender.password = "configured"  # pragma: allowlist secret
    sender.from_email = "service@example"
    return sender


@contextmanager
def _capture(logger: logging.Logger, level: int = logging.INFO):
    """Attach a temporary handler — setup_logger console handlers can miss caplog."""
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


@pytest.mark.asyncio
async def test_api_success_log_contains_count_not_recipient_addresses(monkeypatch):
    async def sent(*_args, **_kwargs):
        return True, "brevo"

    monkeypatch.setattr("app.integrations.email_api.api_available", lambda: True)
    monkeypatch.setattr("app.integrations.email_api.send_email_api", sent)
    monkeypatch.setattr(module, "_integ_ok", lambda *_a, **_k: None)

    with _capture(module.logger, logging.INFO) as records:
        assert await _sender().send_email(
            ["private.owner@example.com", "finance@customer.in"], "Subject", "Body"
        )
        text = "\n".join(records)
        assert "private.owner@example.com" not in text
        assert "finance@customer.in" not in text
        assert "recipients=2" in text


@pytest.mark.asyncio
async def test_smtp_failure_log_and_health_note_redact_exception_recipient(monkeypatch):
    async def failed(*_args, **_kwargs):
        raise RuntimeError("554 Disabled by user for private.owner@example.com")

    notes = []
    monkeypatch.setattr("app.integrations.email_api.api_available", lambda: False)
    monkeypatch.setattr(module.aiosmtplib, "send", failed)
    monkeypatch.setattr(module, "_integ_fail", lambda name, note="": notes.append((name, note)))

    with _capture(module.logger, logging.ERROR) as records:
        with pytest.raises(RuntimeError):
            await _sender().send_email(["private.owner@example.com"], "Subject", "Body")
        text = "\n".join(records)
        assert "private.owner@example.com" not in text
        assert all("private.owner@example.com" not in note for _, note in notes)
        assert "recipients=1" in text
