"""Tests for RFC 8058 one-click unsubscribe (cold-outreach deliverability).

Pure-python: token HMAC + header builders + suppression store (tmp) + a
monkeypatched SMTP send. NO network, NO real DB.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _no_warmup_side_effect(monkeypatch):
    from app.platform import email_warmup

    monkeypatch.setattr(email_warmup, "record_complaint", lambda *a, **k: {"recorded": True})


def test_token_roundtrip_and_case_normalized():
    from app.platform import email_unsub as eu

    tok = eu.make_token("Foo@Example.COM")
    assert eu.verify_token(tok) == "foo@example.com"


def test_verify_rejects_tampered_token():
    from app.platform import email_unsub as eu

    tok = eu.make_token("a@b.com")
    assert eu.verify_token(tok + "x") is None
    assert eu.verify_token("garbage") is None
    assert eu.verify_token("") is None


def test_headers_are_rfc8058_one_click():
    from app.platform import email_unsub as eu

    h = eu.headers_for("user@example.com")
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    lu = h["List-Unsubscribe"]
    assert lu.startswith("<http") and "mailto:" in lu  # URL + mailto, both bracketed
    # blank email -> no headers (caller can splat unconditionally)
    assert eu.headers_for("") == {}


def test_suppress_then_is_suppressed(tmp_path, monkeypatch):
    from app.platform import email_unsub as eu

    monkeypatch.setattr(eu, "_store_path", lambda: tmp_path / "sup.jsonl")
    assert eu.is_suppressed("x@y.com") is False
    assert eu.suppress("X@Y.com", "one_click") is True
    assert eu.is_suppressed("x@y.com") is True  # case-normalized match
    assert eu.is_suppressed("other@z.com") is False


def test_list_suppressed_and_bulk_set_are_never_raise(tmp_path, monkeypatch):
    from app.platform import email_unsub as eu

    store = tmp_path / "sup.jsonl"
    monkeypatch.setattr(eu, "_store_path", lambda: store)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(
        'not-json\n{"email":"old@x.in","reason":"one_click","ts":1}\n', encoding="utf-8"
    )

    assert eu.suppress("New@X.in", "reply_unsubscribe") is True
    rows = eu.list_suppressed()
    assert rows[0]["email"] == "new@x.in"
    assert rows[-1]["email"] == "old@x.in"
    assert eu.suppressed_emails() == {"old@x.in", "new@x.in"}


def test_unsub_url_points_at_lifecycle_route():
    from app.platform import email_unsub as eu

    url = eu.unsub_url("a@b.com")
    assert "/api/lifecycle/outreach-unsub/" in url


def test_send_email_applies_extra_headers(monkeypatch):
    """send_email must put List-Unsubscribe* on the MIME message (SMTP path)."""
    from app.integrations import email_sender as es

    sender = es.EmailSender()
    monkeypatch.setattr(sender, "user", "u", raising=False)
    monkeypatch.setattr(sender, "password", "p", raising=False)

    # Force the SMTP branch (email API unavailable).
    import app.integrations.email_api as eapi

    monkeypatch.setattr(eapi, "api_available", lambda: False, raising=False)

    captured: dict = {}

    async def _fake_send(msg, **kw):
        captured["msg"] = msg
        return None

    monkeypatch.setattr(es.aiosmtplib, "send", _fake_send, raising=False)

    ok = asyncio.run(
        sender.send_email(
            ["x@example.com"],
            "subj",
            "body",
            extra_headers={
                "List-Unsubscribe": "<https://leadsgenai.in/u/abc>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
    )
    assert ok is True
    msg = captured["msg"]
    assert msg["List-Unsubscribe"] == "<https://leadsgenai.in/u/abc>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
