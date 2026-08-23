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
        # TRAI AI-disclosure enforced on custom messages too (audit 2026-07-04):
        # original text preserved, disclosure prepended when missing.
        assert data["message_used"].endswith("Namaste, yeh ek demo call hai.")
        assert "AI" in data["message_used"]
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


class TestStatusWebhookDurationClamp:
    """Vobiz doesn't sign /vobiz/status, so a forged/replayed POST could claim an
    inflated Duration to over-bill voice minutes (production audit 2026-07-01,
    F-SEC1). Regression test for the clamp added in app/telephony/webhooks.py."""

    def test_forged_duration_is_clamped_to_max_call_duration(self, client: TestClient, monkeypatch):
        captured = {}

        class _StubCallManager:
            active_calls: dict = {}

            async def handle_call_completed(self, call_id, duration, recording_url=None):
                captured["duration"] = duration
                return None

        import app.telephony.webhooks as webhooks_module

        monkeypatch.setattr(webhooks_module, "_get_call_manager", lambda: _StubCallManager())
        monkeypatch.setattr(settings, "max_call_duration_seconds", 300, raising=False)

        forged_duration = 999999  # far beyond any real call length
        r = client.post(
            "/api/webhooks/vobiz/status",
            data={
                "CallbackData": "test-call-clamp-1",
                "Status": "completed",
                "Duration": str(forged_duration),
            },
        )
        assert r.status_code == 200
        assert captured["duration"] == 300  # clamped, not the forged 999999

    def test_normal_duration_passes_through_unclamped(self, client: TestClient, monkeypatch):
        captured = {}

        class _StubCallManager:
            active_calls: dict = {}

            async def handle_call_completed(self, call_id, duration, recording_url=None):
                captured["duration"] = duration
                return None

        import app.telephony.webhooks as webhooks_module

        monkeypatch.setattr(webhooks_module, "_get_call_manager", lambda: _StubCallManager())
        monkeypatch.setattr(settings, "max_call_duration_seconds", 300, raising=False)

        r = client.post(
            "/api/webhooks/vobiz/status",
            data={
                "CallbackData": "test-call-clamp-2",
                "Status": "completed",
                "Duration": "45",
            },
        )
        assert r.status_code == 200
        assert captured["duration"] == 45


class TestLeadPhoneThreading:
    """2026-07-03 — the dialed number must survive the full outbound chain
    (start_stream_call -> answer_url -> WS session) so close-signal durable
    actions (deal write + WhatsApp send) have a phone on OUTBOUND calls.
    Vobiz's start event has NO customParameters (confirmed from raw#1 logs on
    a real call), so before this the session's _lead_phone stayed None and
    every close/onboard action silently no-op'd on real campaign calls."""

    def test_answer_stream_qs_carries_lead_phone(self):
        from app.api.telephony_vobiz import _answer_stream_qs

        qs = _answer_stream_qs("ai_marketing", None, lead_phone="+919876543210")
        assert "lead_phone=%2B919876543210" in qs

    def test_session_accepts_lead_phone_kwarg(self):
        from app.telephony.vobiz_stream import VobizStreamSession

        s = VobizStreamSession.__new__(VobizStreamSession)
        VobizStreamSession.__init__(
            s, websocket=None, niche="ai_marketing", lead_phone="+919876543210"
        )
        assert s._lead_phone == "+919876543210"

    def test_answer_stream_xml_passes_lead_phone_to_ws_url(self, client: TestClient):
        r = client.get(
            "/api/telephony/vobiz/answer-stream/testtok123"
            "?niche=ai_marketing&lead_phone=%2B919876543210"
        )
        assert r.status_code == 200
        assert "lead_phone=%2B919876543210" in r.text


class TestStreamOptOut:
    """TCCCPR stream-path opt-out (audit 2026-07-04): press-9/verbal revocation
    on LIVE stream calls must persist to the consent ledger — previously only
    the legacy answer_url path did."""

    def _session(self, phone="+919876543210"):
        from app.telephony.vobiz_stream import VobizStreamSession

        s = VobizStreamSession.__new__(VobizStreamSession)
        VobizStreamSession.__init__(s, websocket=None, niche="ai_marketing", lead_phone=phone)
        return s

    def test_opt_out_regex_matches_revocations(self):
        s = self._session()
        for txt in (
            "stop calling me",
            "don't call again",
            "dobara call mat karna",
            "call mat karo mujhe",
            "mera number hatao",
            "unsubscribe karo",
        ):
            assert s._is_opt_out(txt), txt

    def test_opt_out_regex_ignores_callback_asks(self):
        s = self._session()
        for txt in (
            "abhi busy hoon, baad me call karna",  # callback ask, NOT revocation
            "haan interested hoon",
            "kal call karna theek rahega",
            "",
        ):
            assert not s._is_opt_out(txt), txt

    def test_persist_opt_out_records_to_ledger(self, monkeypatch):
        import app.telephony.consent_ledger as cl

        calls = []
        monkeypatch.setattr(cl, "record_opt_out", lambda phone, **kw: calls.append((phone, kw)))
        s = self._session()
        s._persist_opt_out("verbal_request")
        assert len(calls) == 1
        assert calls[0][0] == "+919876543210"
        assert calls[0][1]["reason"] == "verbal_request"

    def test_persist_opt_out_no_phone_is_noop(self, monkeypatch):
        import app.telephony.consent_ledger as cl

        calls = []
        monkeypatch.setattr(cl, "record_opt_out", lambda phone, **kw: calls.append(phone))
        s = self._session(phone="")
        s._persist_opt_out("ivr_press9")
        assert calls == []
