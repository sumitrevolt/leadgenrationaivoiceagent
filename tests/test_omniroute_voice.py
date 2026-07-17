"""Tests for app.voice_agent.omniroute_voice — voice-scoped OmniRoute wrapper."""

from __future__ import annotations

import pytest

from app.platform.safe_ai_payload import SafePayloadError
from app.voice_agent import omniroute_voice as ov


class TestOmniRouteVoiceInert:
    def test_voice_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("OMNIROUTE_VOICE", raising=False)
        assert ov.voice_enabled() is False

    def test_voice_requires_omniroute_enabled_and_key(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_VOICE", "1")
        monkeypatch.delenv("OMNIROUTE_ENABLED", raising=False)
        assert ov.voice_enabled() is False
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
        assert ov.voice_enabled() is False

    @pytest.mark.asyncio
    async def test_chat_stream_empty_when_disabled(self, monkeypatch):
        monkeypatch.delenv("OMNIROUTE_VOICE", raising=False)
        out = []
        async for tok in ov.chat_stream("", [{"role": "user", "content": "hi"}]):
            out.append(tok)
        assert out == []


class TestOmniRouteVoiceStreaming:
    @pytest.mark.asyncio
    async def test_stream_masks_phone_and_yields_tokens(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_VOICE", "1")
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        seen = {}

        class _Delta:
            def __init__(self, content: str):
                self.content = content

        class _Choice:
            def __init__(self, content: str):
                self.delta = _Delta(content)

        class _Chunk:
            def __init__(self, content: str):
                self.choices = [_Choice(content)]

        class _FakeStream:
            def __init__(self, chunks):
                self._chunks = list(chunks)

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self._chunks:
                    raise StopAsyncIteration
                return self._chunks.pop(0)

            async def aclose(self):
                return None

        class _FakeCompletions:
            async def create(self, **kwargs):
                seen.update(kwargs)
                return _FakeStream([_Chunk("Namaste "), _Chunk("sir")])

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeClient:
            chat = _FakeChat()

        monkeypatch.setattr("app.platform.omniroute_client.omniroute_client", lambda: _FakeClient())
        gen_id = ov.new_generation_id()
        parts = []
        async for t in ov.chat_stream(
            "",
            [{"role": "user", "content": "Call 9876543210 about pricing"}],
            generation_id=gen_id,
        ):
            parts.append(t)
        assert "".join(parts) == "Namaste sir"
        payload = str(seen.get("messages"))
        assert "9876543210" not in payload
        assert "[PHONE REDACTED]" in payload

    @pytest.mark.asyncio
    async def test_cancel_generation_blocks_before_network(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_VOICE", "1")
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")

        def _boom():
            raise AssertionError("network should not be called when pre-cancelled")

        monkeypatch.setattr("app.platform.omniroute_client.omniroute_client", _boom)
        gen_id = ov.new_generation_id()
        ov.cancel_generation(gen_id)
        parts = []
        async for t in ov.chat_stream(
            "", [{"role": "user", "content": "hi"}], generation_id=gen_id
        ):
            parts.append(t)
        assert parts == []


class TestSwaraLiveRoute:
    def test_swara_live_route_registered(self):
        from app.platform.omniroute_client import get_task_route

        route = get_task_route(ov.TASK_SWARA_LIVE, ov.PRIVACY_CUSTOMER_MASKED)
        assert route.primary_model == "leadgen-free-first"
        assert route.privacy_class == "CUSTOMER_MASKED"

    def test_wrong_privacy_rejected(self):
        from app.platform.omniroute_client import get_task_route

        with pytest.raises(SafePayloadError):
            get_task_route(ov.TASK_SWARA_LIVE, "INTERNAL_SANITIZED")
