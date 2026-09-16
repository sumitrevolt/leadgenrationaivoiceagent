"""P0 regression: POST /api/webhooks/telegram exists, verifies the secret
fail-closed, dedups by update_id, persists durably, and handles opt-out.

No network, no app-level consumers required — the surface is tested in isolation.
"""
import json
import os
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
# run the app with a clean, deterministic env for the telegram secret
os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _update(update_id, text="hi", chat_id=123):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id, "first_name": "Owner"},
            "text": text,
        },
    }


def test_post_returns_200_not_405(client, monkeypatch, tmp_path):
    """The P0: POST must be handled (was 405 on prod)."""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "unit-secret-abc")
    # route inbox to tmp so we don't write into repo data/
    import app.api.webhooks as wh
    monkeypatch.setattr(wh, "_telegram_inbox_path", lambda: str(tmp_path / "inbox.jsonl"))
    r = client.post(
        "/api/webhooks/telegram",
        json=_update(100, "hello owner"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "unit-secret-abc"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["update_id"] == 100
    # durable persist happened
    inbox = tmp_path / "inbox.jsonl"
    assert inbox.exists()
    assert len(json.loads(inbox.read_text().strip().splitlines()[-1])["update"]) >= 1


def test_post_bad_secret_is_refused(client, monkeypatch, tmp_path):
    """When TELEGRAM_WEBHOOK_SECRET is set, a mismatch MUST be refused (fail-closed)."""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "correct-secret")
    import app.api.webhooks as wh
    monkeypatch.setattr(wh, "_telegram_inbox_path", lambda: str(tmp_path / "inbox.jsonl"))
    r = client.post(
        "/api/webhooks/telegram",
        json=_update(200, "hi"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "WRONG"},
    )
    assert r.status_code == 200  # still 200 to stop retries, but flagged not-ok
    assert r.json() == {"ok": False, "reason": "bad_secret"}
    # must NOT have persisted a bad-secret payload
    assert not (tmp_path / "inbox.jsonl").exists()


def test_post_dedup_by_update_id(client, monkeypatch, tmp_path):
    """A retried identical update_id is deduped (Telegram retries reuse ids)."""
    import app.api.webhooks as wh
    monkeypatch.setattr(wh, "_telegram_inbox_path", lambda: str(tmp_path / "inbox.jsonl"))
    wh._telegram_seen.clear()
    h = {}
    r1 = client.post("/api/webhooks/telegram", json=_update(300, "msg"), headers=h)
    r2 = client.post("/api/webhooks/telegram", json=_update(300, "msg"), headers=h)
    assert r1.json().get("dedup") is not True  # first call: key absent or False
    assert r2.json() == {"ok": True, "dedup": True, "update_id": 300}


def test_opt_out_stops_suppression(client, monkeypatch, tmp_path, caplog):
    """'STOP' -> opt-out flagged + cross-channel suppression invoked (best-effort)."""
    import app.api.webhooks as wh
    monkeypatch.setattr(wh, "_telegram_inbox_path", lambda: str(tmp_path / "inbox.jsonl"))
    calls = []
    import app.telephony.consent_ledger as cl
    monkeypatch.setattr(cl, "record_opt_out", lambda phone, reason="", channel="", call_id="": calls.append((phone, channel)))
    r = client.post("/api/webhooks/telegram", json=_update(400, "STOP", chat_id=918261030181), headers={})
    assert r.status_code == 200
    assert r.json()["opt_out"] is True
    assert calls and calls[0][1] == "telegram"


def test_get_verify_returns_200(client):
    """GET (URL-registration probe) returns 200, not an error."""
    r = client.get("/api/webhooks/telegram")
    assert r.status_code == 200
    assert r.json()["ok"] is True
