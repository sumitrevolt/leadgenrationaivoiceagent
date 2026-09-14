"""Pins for the Meta Cloud webhook verification hardening (2026-09-14).

Three concrete gaps this locks down (Deliverable A of the WhatsApp-Cloud audit):

  1. ``/api/wa/webhook`` GET read ``WHATSAPP_VERIFY_TOKEN`` from raw ``os.getenv`` only,
     so a container that injects a SUBSET of the host env 403'd Meta's handshake even
     though the token WAS configured (Settings loads ``.env``). Its sibling
     (``app/api/webhooks.py::_wa_verify_token``) already read Settings first.
  2. Both GET handshakes compared the verify token with ``==``. It is a shared secret,
     so it now goes through ``verify_webhook_token`` (``hmac.compare_digest``,
     fail-CLOSED on unset/non-ASCII).
  3. ``/api/wa/webhook`` POST wrapped signature verification in ``except: pass`` — any
     error while reading/verifying let the payload through UNVERIFIED. It now denies.

No network, no credentials. The valid-signature case stubs ``reply_agent.whatsapp_reply``
so nothing ever reaches an LLM.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.integrations import whatsapp as wa


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _payload(from_number: str = "919876543210", text: str = "price batao") -> bytes:
    return json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": from_number,
                                        "id": "wamid.TEST",
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()


# --------------------------------------------------------------------------- #
# verify_webhook_token — the shared constant-time compare
# --------------------------------------------------------------------------- #
def test_verify_webhook_token_matches_and_rejects():
    assert wa.verify_webhook_token("tok123", "tok123") is True
    assert wa.verify_webhook_token("wrong", "tok123") is False
    assert wa.verify_webhook_token(None, "tok123") is False


def test_verify_webhook_token_fails_closed_when_unset():
    """No configured token == nobody passes the handshake."""
    assert wa.verify_webhook_token("tok123", "") is False
    assert wa.verify_webhook_token("tok123", None) is False
    assert wa.verify_webhook_token("", "") is False


def test_verify_webhook_token_never_raises_on_non_ascii():
    """compare_digest raises TypeError on non-ASCII str — must deny, not 500."""
    assert wa.verify_webhook_token("tökén", "tok123") is False


# --------------------------------------------------------------------------- #
# GET handshake — Settings-first token + constant-time compare
# --------------------------------------------------------------------------- #
def _handshake(token: str) -> dict:
    return {"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "999"}


def test_handshake_ok_from_settings_with_env_unset(client, monkeypatch):
    from app.api import whatsapp as api_wa

    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN", raising=False)
    monkeypatch.setattr(api_wa.settings, "whatsapp_verify_token", "tok123", raising=False)
    r = client.get("/api/wa/webhook", params=_handshake("tok123"))
    assert r.status_code == 200
    assert r.text == "999"


def test_handshake_rejects_wrong_token(client, monkeypatch):
    from app.api import whatsapp as api_wa

    monkeypatch.setattr(api_wa.settings, "whatsapp_verify_token", "tok123", raising=False)
    r = client.get("/api/wa/webhook", params=_handshake("WRONG"))
    assert r.status_code == 403


def test_handshake_rejects_when_token_unconfigured(client, monkeypatch):
    from app.api import whatsapp as api_wa

    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN", raising=False)
    monkeypatch.setattr(api_wa.settings, "whatsapp_verify_token", "", raising=False)
    r = client.get("/api/wa/webhook", params=_handshake(""))
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# POST — signature gate is fail-CLOSED
# --------------------------------------------------------------------------- #
def test_post_rejects_bad_signature_when_secret_set(client, monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "topsecret")
    r = client.post(
        "/api/wa/webhook",
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
        content=_payload(),
    )
    assert r.status_code == 200
    assert r.json() == {"ok": False, "reason": "bad_signature"}


def test_post_fails_closed_when_verifier_errors(client, monkeypatch):
    """An exception inside the verify block must DENY — it used to fall through."""

    def _boom(raw, sig):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(wa, "verify_meta_signature", _boom)
    r = client.post(
        "/api/wa/webhook", headers={"Content-Type": "application/json"}, content=_payload()
    )
    assert r.status_code == 200
    assert r.json() == {"ok": False, "reason": "bad_signature"}


def test_post_accepts_valid_signature(client, monkeypatch, tmp_path):
    """Sanity: the gate is a check, not a blanket deny."""
    monkeypatch.chdir(tmp_path)  # _store_inbound writes data/wa_inbound.jsonl
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "topsecret")

    from app.platform import reply_agent

    async def _fake_reply(*_a, **_k):
        return {}

    monkeypatch.setattr(reply_agent, "whatsapp_reply", _fake_reply)

    body = _payload()
    sig = "sha256=" + hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    r = client.post(
        "/api/wa/webhook",
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        content=body,
    )
    assert r.status_code == 200
    res = r.json()
    assert res["ok"] is True
    assert res["messages"] == 1
