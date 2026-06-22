"""
Tests: Vobiz telephony — XML builder, answer webhook, test-call endpoint.
No network — VobizClient methods are monkeypatched; tests always pass an
explicit `message` so the LLM path is never exercised.
"""

from fastapi.testclient import TestClient

from app.config import settings
from app.telephony.vobiz_handler import VobizClient, build_speak_xml


class TestBuildSpeakXml:
    def test_contains_speak_and_hangup(self):
        xml = build_speak_xml("Namaste from LeadGen AI")
        assert "<Response>" in xml
        assert "<Speak" in xml
        assert "<Hangup/>" in xml
        assert "Namaste from LeadGen AI" in xml
        # NOTE: voice/language attributes intentionally REMOVED (2026-06-07) —
        # Vobiz silently drops Speak verbs carrying unsupported attrs (caused
        # "call connects then instantly hangs up"). Minimal <Speak>text</Speak>.
        assert "<Speak>" in xml
        assert "language=" not in xml

    def test_escapes_special_chars(self):
        xml = build_speak_xml("R&D <test> calls")
        assert "R&amp;D" in xml
        assert "&lt;test&gt;" in xml
        assert "<test>" not in xml

    def test_empty_text_still_valid(self):
        xml = build_speak_xml("")
        assert "<Speak" in xml and "<Hangup/>" in xml


class TestAnswerWebhook:
    def test_unknown_token_returns_200_xml_with_speak(self, client: TestClient):
        r = client.get("/api/telephony/vobiz/answer/random0token")
        assert r.status_code == 200
        assert "application/xml" in r.headers["content-type"]
        assert "<Speak" in r.text
        assert "<Hangup/>" in r.text

    def test_post_method_also_served(self, client: TestClient):
        r = client.post("/api/telephony/vobiz/answer/random0token")
        assert r.status_code == 200
        assert "<Speak" in r.text


class TestTestCall:
    def test_503_when_vobiz_not_configured(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(settings, "vobiz_auth_id", "", raising=False)
        monkeypatch.setattr(settings, "vobiz_auth_token", "", raising=False)
        r = client.post(
            "/api/telephony/vobiz/test-call",
            json={"to": "+919876543210", "message": "hi"},
        )
        assert r.status_code == 503

    def test_placed_true_with_mocked_client(self, client: TestClient, monkeypatch):
        captured = {}

        async def fake_place_call(self, to, answer_url, from_=None, **extra):
            captured["to"] = to
            captured["answer_url"] = answer_url
            return {"status_code": 201, "body": {}}

        monkeypatch.setattr(VobizClient, "available", lambda self: True)
        monkeypatch.setattr(VobizClient, "place_call", fake_place_call)

        r = client.post(
            "/api/telephony/vobiz/test-call",
            json={
                "to": "+919876543210",
                "niche": "solar_residential",
                "message": "Namaste, yeh ek demo call hai.",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["placed"] is True
        assert data["message_used"] == "Namaste, yeh ek demo call hai."
        assert data["vobiz_response"]["status_code"] == 201
        assert "/api/telephony/vobiz/answer/" in data["answer_url"]
        assert captured["to"] == "+919876543210"
        assert captured["answer_url"] == data["answer_url"]

    def test_placed_false_on_error_status(self, client: TestClient, monkeypatch):
        async def fake_place_call(self, to, answer_url, from_=None, **extra):
            return {"status_code": 401, "body": {"error": "unauthorized"}}

        monkeypatch.setattr(VobizClient, "available", lambda self: True)
        monkeypatch.setattr(VobizClient, "place_call", fake_place_call)

        r = client.post(
            "/api/telephony/vobiz/test-call",
            json={"to": "+919876543210", "message": "hi there"},
        )
        assert r.status_code == 200
        assert r.json()["placed"] is False


class TestStatus:
    def test_status_shape_without_network(self, client: TestClient, monkeypatch):
        async def fake_balance(self):
            return {"status_code": 200, "body": {"balance": "25.00"}}

        monkeypatch.setattr(VobizClient, "get_balance", fake_balance)
        r = client.get("/api/telephony/vobiz/status")
        assert r.status_code == 200
        data = r.json()
        for key in ("available", "trunk_id", "domain", "caller_id_set", "balance"):
            assert key in data
        # balance is fetched only when configured; both states are valid here
        if data["available"]:
            assert data["balance"]["status_code"] == 200
        else:
            assert data["balance"] is None
