"""Admin manual customer-call UI + canonical Vobiz stream-call contract."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.telephony.vobiz_handler import VobizClient


def _admin_html() -> str:
    return Path("frontend/admin_dashboard.html").read_text(encoding="utf-8")


def test_admin_manual_call_card_is_prominent_and_uses_canonical_route() -> None:
    html = _admin_html()

    assert 'id="manualCallCard"' in html
    assert 'href="#manualCallCard"' in html
    assert 'id="manualCallPhone"' in html
    assert 'id="manualCallNiche"' in html
    assert 'value="ai_marketing" selected' in html
    assert 'id="manualCallType"' in html
    assert 'id="manualCallConfirm"' in html
    assert 'id="manualCallBtn"' in html
    assert 'id="manualCallResult"' in html
    assert 'fetch("/api/telephony/vobiz/stream-call"' in html


def test_admin_manual_call_ui_keeps_required_safety_controls() -> None:
    html = _admin_html()

    assert "call_type: callType" in html
    assert "niche: niche" in html
    assert "to: phone" in html
    assert "normalizeManualCallPhone" in html
    assert "manualCallInFlight" in html
    assert "manualCallCooldownUntil" in html
    assert "AbortController" in html
    assert "confirm(" in html
    assert 'value="transactional"' in html
    assert 'value="promotional"' in html


def test_manual_stream_call_passes_explicit_type_and_marketing_niche(
    client: TestClient, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    async def fake_place_call(self, to, answer_url, from_=None, **extra):
        captured.update(to=to, answer_url=answer_url, extra=extra)
        return {
            "status_code": 201,
            "body": {"message": "call queued", "request_uuid": "manual-call-1"},
        }

    monkeypatch.setattr(VobizClient, "available", lambda self: True)
    monkeypatch.setattr(VobizClient, "place_call", fake_place_call)

    response = client.post(
        "/api/telephony/vobiz/stream-call",
        json={
            "to": "+918459433410",
            "niche": "ai_marketing",
            "call_type": "transactional",
        },
    )

    assert response.status_code == 200
    assert response.json()["placed"] is True
    assert captured["to"] == "+918459433410"
    assert captured["extra"]["call_type"] == "transactional"
    assert captured["extra"]["hangup_method"] == "POST"
    assert "/api/webhooks/vobiz/status" in captured["extra"]["hangup_url"]
    assert "niche=ai_marketing" in str(captured["answer_url"])


def test_manual_stream_call_surfaces_compliance_block(client: TestClient, monkeypatch) -> None:
    async def blocked_place_call(self, to, answer_url, from_=None, **extra):
        return {
            "status_code": 422,
            "blocked": True,
            "compliance": {"allowed": False, "reason": "dnd_blocked"},
        }

    monkeypatch.setattr(VobizClient, "available", lambda self: True)
    monkeypatch.setattr(VobizClient, "place_call", blocked_place_call)

    response = client.post(
        "/api/telephony/vobiz/stream-call",
        json={
            "to": "+918459433410",
            "niche": "ai_marketing",
            "call_type": "promotional",
        },
    )

    assert response.status_code == 422
    detail = response.json()["error"]["message"]
    assert detail["error"] == "Call blocked by compliance gate (TCCCPR/TRAI)."
    assert detail["compliance"]["reason"] == "dnd_blocked"


def test_manual_stream_call_uses_the_smartflo_rail_when_tata_is_active(
    client: TestClient, monkeypatch
) -> None:
    """The admin manual-call card is the owner's primary dial surface. It used to
    hardcode VobizClient and 503 on a Smartflo-only prod, so a correctly
    configured Smartflo account could not place a manual AI call at all."""
    monkeypatch.setenv("TELEPHONY_PROVIDER", "tata_smartflo")
    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "test-token")
    monkeypatch.setenv("TATA_SMARTFLO_API_KEY", "test-key")

    captured: dict[str, object] = {}

    class _FakeSmartfloClient:
        def available(self):
            return True

        async def place_call(self, **kwargs):
            captured.update(kwargs)
            return {"status_code": 200, "body": {"success": True, "ref_id": "SF_REF_1"}}

    class _BoomVobizClient:
        def __init__(self):
            raise AssertionError("Smartflo rail must not instantiate VobizClient")

    monkeypatch.setattr("app.api.telephony_vobiz.VobizClient", _BoomVobizClient)
    monkeypatch.setattr(
        "app.telephony.tata_smartflo_handler.TataSmartfloClient", _FakeSmartfloClient
    )

    response = client.post(
        "/api/telephony/vobiz/stream-call",
        json={
            "to": "+918459433410",
            "niche": "ai_marketing",
            "call_type": "transactional",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["placed"] is True
    assert body["provider"] == "tata_smartflo"
    assert body["stream_token"]
    assert captured["to"] == "+918459433410"
    assert captured["call_type"] == "transactional"
    assert captured["custom_identifier"]["niche"] == "ai_marketing"


def test_manual_stream_call_surfaces_a_smartflo_compliance_block(
    client: TestClient, monkeypatch
) -> None:
    """Same 422 contract as the Vobiz rail — a pre-dial refusal must never look
    like a placed call."""
    monkeypatch.setenv("TELEPHONY_PROVIDER", "tata_smartflo")
    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "test-token")
    monkeypatch.setenv("TATA_SMARTFLO_API_KEY", "test-key")

    class _BlockedSmartfloClient:
        def available(self):
            return True

        async def place_call(self, **kwargs):
            return {"status_code": 0, "body": {"error": "compliance_blocked: dnd_blocked"}}

    monkeypatch.setattr(
        "app.telephony.tata_smartflo_handler.TataSmartfloClient", _BlockedSmartfloClient
    )

    response = client.post(
        "/api/telephony/vobiz/stream-call",
        json={
            "to": "+918459433410",
            "niche": "ai_marketing",
            "call_type": "promotional",
        },
    )

    assert response.status_code == 422
    detail = response.json()["error"]["message"]
    assert detail["error"] == "Call blocked by compliance gate (TCCCPR/TRAI)."
