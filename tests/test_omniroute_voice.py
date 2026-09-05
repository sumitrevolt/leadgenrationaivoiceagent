"""Tests for app.voice_agent.omniroute_voice — voice-scoped OmniRoute wrapper."""

from __future__ import annotations

import pytest

from app.platform.safe_ai_payload import SafePayloadError
from app.voice_agent import omniroute_voice as ov


@pytest.fixture(autouse=True)
def _reset_voice_breaker():
    ov.reset_breaker()
    yield
    ov.reset_breaker()


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
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "OWNER DIRECTIVE 2026-08-23 pins voice to leadgen-swara-flagship, but "
            "2026-09-04 live probe of VPS gateway /v1/models (505 ids) does NOT list "
            "that combo — routing voice there would 404 the hot path. Swara surface "
            "is FROZEN (no code edit without owner). Owner decision: re-create the "
            "combo on the VPS gateway, then unmark. Code currently keeps "
            "hermes-voice (gateway-verified id)."
        ),
    )
    def test_swara_live_route_registered(self):
        from app.platform.omniroute_client import get_task_route

        route = get_task_route(ov.TASK_SWARA_LIVE, ov.PRIVACY_CUSTOMER_MASKED)
        # 2026-08-23 OWNER DIRECTIVE: voice hot-path pinned to the flagship combo
        # `leadgen-swara-flagship` (antigravity Gemini 3.1 Pro / Claude Opus 4.6
        # head, smoke 200). Old swara-live (groq->mistral->gemini) stays in the
        # gateway DB as fallback; client-side fallback = groq gpt-oss-120b.
        assert route.primary_model == "leadgen-swara-flagship"
        assert route.fallback_model == "groq/openai/gpt-oss-120b"
        assert route.privacy_class == "CUSTOMER_MASKED"

    def test_wrong_privacy_rejected(self):
        from app.platform.omniroute_client import get_task_route

        with pytest.raises(SafePayloadError):
            get_task_route(ov.TASK_SWARA_LIVE, "INTERNAL_SANITIZED")


class TestOmniRouteSingleRoute:
    @pytest.mark.asyncio
    async def test_omniroute_single_route_shared_generation_id(self, monkeypatch):
        """Telecaller-owned gen_id: free_ai realtime must not re-attempt OmniRoute."""
        from app.voice_agent import free_ai

        monkeypatch.setenv("OMNIROUTE_VOICE", "1")
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")

        omni_calls: list[str | None] = []

        async def fake_omni_chat_stream(*args, **kwargs):
            omni_calls.append(kwargs.get("generation_id"))
            if False:
                yield "tok"

        monkeypatch.setattr(ov, "chat_stream", fake_omni_chat_stream)

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
            def __aiter__(self):
                return self

            async def __anext__(self):
                if getattr(self, "_done", False):
                    raise StopAsyncIteration
                self._done = True
                return _Chunk("fallback")

            async def aclose(self):
                return None

        class _FakeCompletions:
            async def create(self, **kwargs):
                return _FakeStream()

        class _FakeClient:
            chat = type("Chat", (), {"completions": _FakeCompletions()})()

        monkeypatch.setattr(
            "app.voice_agent.free_ai._build_llm_chain", lambda _prof: [("groq", "x")]
        )
        monkeypatch.setattr("app.voice_agent.free_ai._client", lambda _p: _FakeClient())
        monkeypatch.setattr("app.voice_agent.free_ai._provider_down", lambda _p: False)
        monkeypatch.setattr("app.voice_agent.free_ai._blocked_for_provider", lambda _m, _p: False)

        gen_id = ov.new_generation_id()
        async for _ in ov.chat_stream(
            "", [{"role": "user", "content": "price kya hai"}], generation_id=gen_id
        ):
            pass

        got_free = False
        async for _ in free_ai.chat_stream(
            "",
            [{"role": "user", "content": "price kya hai"}],
            max_tokens=16,
            profile="realtime",
        ):
            got_free = True
            break

        assert got_free is True
        assert len(omni_calls) == 1
        assert omni_calls[0] == gen_id


class TestGatewayBreaker:
    """A dead gateway must not burn the voice turn's latency budget every turn."""

    @staticmethod
    def _enable(monkeypatch):
        monkeypatch.setenv("OMNIROUTE_VOICE", "1")
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")

    @pytest.mark.asyncio
    async def test_dead_gateway_trips_breaker_and_stops_retrying(self, monkeypatch):
        self._enable(monkeypatch)
        monkeypatch.setenv("OMNIROUTE_VOICE_BREAKER_FAILS", "2")
        attempts = {"n": 0}

        class _FakeCompletions:
            async def create(self, **kwargs):
                attempts["n"] += 1
                raise ConnectionError("gateway refused")

        class _FakeClient:
            chat = type("Chat", (), {"completions": _FakeCompletions()})()

        monkeypatch.setattr("app.platform.omniroute_client.omniroute_client", lambda: _FakeClient())

        for _ in range(2):
            async for _tok in ov.chat_stream("", [{"role": "user", "content": "hi"}]):
                pass

        assert ov.breaker_open() is True
        burned = attempts["n"]
        assert burned > 0

        # Quarantined: fail-open to free_ai instantly, zero gateway round-trips.
        text, meta = await ov.chat("", [{"role": "user", "content": "hi"}])
        assert (text, meta) == ("", None)
        assert attempts["n"] == burned

    @pytest.mark.asyncio
    async def test_healthy_stream_resets_breaker(self, monkeypatch):
        self._enable(monkeypatch)
        ov._breaker["fails"] = 1.0

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
            def __init__(self):
                self._chunks = [_Chunk("Namaste")]

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
                return _FakeStream()

        class _FakeClient:
            chat = type("Chat", (), {"completions": _FakeCompletions()})()

        monkeypatch.setattr("app.platform.omniroute_client.omniroute_client", lambda: _FakeClient())

        parts = []
        async for tok in ov.chat_stream("", [{"role": "user", "content": "hi"}]):
            parts.append(tok)

        assert "".join(parts) == "Namaste"
        assert ov._breaker["fails"] == 0.0
        assert ov.breaker_open() is False


class TestCancelledBounded:
    def test_cancelled_dict_bounded(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_VOICE_CANCELLED_MAX", "32")
        ov._cancelled.clear()
        for i in range(50):
            ov.cancel_generation(f"gen{i:04d}")
        assert len(ov._cancelled) <= 32
