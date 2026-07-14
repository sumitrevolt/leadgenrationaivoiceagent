"""Delivery logs must prove outcomes without retaining recipient PII."""

from __future__ import annotations

import logging

import pytest

from app.integrations import email_sender as module


def _sender() -> module.EmailSender:
    sender = module.EmailSender.__new__(module.EmailSender)
    sender.host = "smtp.example"
    sender.port = 465
    sender.user = "service-user"
    setattr(sender, "password", "configured")  # synthetic test-only value
    sender.from_email = "service@example"
    return sender


@pytest.mark.asyncio
async def test_api_success_log_contains_count_not_recipient_addresses(monkeypatch, caplog):
    async def sent(*_args, **_kwargs):
        return True, "brevo"

    monkeypatch.setattr("app.integrations.email_api.api_available", lambda: True)
    monkeypatch.setattr("app.integrations.email_api.send_email_api", sent)
    monkeypatch.setattr(module, "_integ_ok", lambda *_a, **_k: None)
    caplog.set_level(logging.INFO)

    assert await _sender().send_email(
        ["private.owner@example.com", "finance@customer.in"], "Subject", "Body"
    )

    text = caplog.text
    assert "private.owner@example.com" not in text
    assert "finance@customer.in" not in text
    assert "recipients=2" in text


@pytest.mark.asyncio
async def test_smtp_failure_log_and_health_note_redact_exception_recipient(monkeypatch, caplog):
    async def failed(*_args, **_kwargs):
        raise RuntimeError("554 Disabled by user for private.owner@example.com")

    notes = []
    monkeypatch.setattr("app.integrations.email_api.api_available", lambda: False)
    monkeypatch.setattr(module.aiosmtplib, "send", failed)
    monkeypatch.setattr(module, "_integ_fail", lambda name, note="": notes.append((name, note)))
    caplog.set_level(logging.ERROR)

    with pytest.raises(RuntimeError):
        await _sender().send_email(["private.owner@example.com"], "Subject", "Body")

    assert "private.owner@example.com" not in caplog.text
    assert all("private.owner@example.com" not in note for _, note in notes)
    assert "recipients=1" in caplog.text
