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
    """The route delegates to ``start_stream_call`` (SmartFlo is sole provider
    since 2026-09-15), so that is the seam to stub. This test used to stub a
    ``VobizClient.place_call`` the route no longer calls at all, which made the
    assertions unfalsifiable — it passed on an inert monkeypatch and only broke
    once the SmartFlo readiness fail-fast started returning 503 first."""
    import app.api.telephony_vobiz as tv

    captured: dict[str, object] = {}

    async def fake_start_stream_call(
        to, niche="general", client_id=None, call_type="transactional", *, lead_id=None, **kw
    ):
        captured.update(to=to, niche=niche, call_type=call_type, client_id=client_id)
        return {"placed": True, "provider": "tata_smartflo", "stream_token": "manual-call-1"}

    # Clear the readiness fail-fast (503) so the request reaches the seam.
    monkeypatch.setattr(tv, "stream_provider_ready", lambda: (True, ""))
    monkeypatch.setattr(tv, "start_stream_call", fake_start_stream_call)

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
    assert captured["call_type"] == "transactional"
    assert captured["niche"] == "ai_marketing"


def test_manual_stream_call_surfaces_compliance_block(client: TestClient, monkeypatch) -> None:
    """A SmartFlo pre-dial refusal (``error == "compliance_blocked"``) must map to
    HTTP 422 with the TCCCPR/TRAI message — the contract the campaign dialer and
    the owner's manual-call card both depend on."""
    import app.api.telephony_vobiz as tv

    async def blocked_start_stream_call(
        to, niche="general", client_id=None, call_type="transactional", *, lead_id=None, **kw
    ):
        return {
            "placed": False,
            "error": "compliance_blocked",
            "provider": "tata_smartflo",
            "smartflo_response": {
                "status_code": 0,
                # The route surfaces `smartflo_response["body"]` verbatim as the
                # 422 `compliance` payload, so the reason must live at that level.
                "body": {
                    "error": "compliance_blocked: dnd_scrub",
                    "reason": "dnd_blocked",
                },
            },
        }

    monkeypatch.setattr(tv, "stream_provider_ready", lambda: (True, ""))
    monkeypatch.setattr(tv, "start_stream_call", blocked_start_stream_call)

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
