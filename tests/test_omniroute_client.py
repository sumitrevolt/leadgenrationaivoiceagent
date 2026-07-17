"""Test app/platform/omniroute_client.py — must stay fully INERT by default.

Audit 2026-07-12. Sumit's OmniRoute instance has no admin auth configured, so this
module must never attempt a real network call unless explicitly enabled+keyed.
"""

import httpx
import pytest

from app.platform.omniroute_client import (
    OmniRouteRoute,
    generate,
    get_task_route,
    omniroute_available,
    omniroute_client,
    omniroute_enabled,
)
from app.platform.safe_ai_payload import SafePayloadError


class TestOmniRouteInertByDefault:
    def test_disabled_by_default_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("OMNIROUTE_ENABLED", raising=False)
        assert omniroute_enabled() is False
        assert omniroute_available() is False
        assert omniroute_client() is None

    def test_enabled_flag_alone_is_not_enough_without_key(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
        assert omniroute_enabled() is True
        assert omniroute_available() is False  # conservative: no key = unavailable
        assert omniroute_client() is None

    def test_enabled_and_keyed_reports_available(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        assert omniroute_available() is True

    def test_never_raises_on_missing_openai_or_bad_state(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_ENABLED", "0")
        # Should just return None, never throw, regardless of other env state.
        assert omniroute_client() is None


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "test response error",
                request=httpx.Request("POST", "http://test/v1/responses"),
                response=httpx.Response(self.status_code),
            )


class TestOmniRouteResponsesAdapter:
    def test_registry_exposes_only_sanitized_dev_routes(self):
        route = get_task_route("leadgen.coding_primary", "INTERNAL_SANITIZED")
        # 2026-07-16: gateway v3.8.48 rebuild — custom combo `leadgen-free-first`
        # PRIMARY (4-deep priority failover: free deepseek → groq → mistral →
        # gemini, PONG-proven) + free auto-alias client-side FALLBACK.
        assert route == OmniRouteRoute(
            primary_model="leadgen-free-first",
            fallback_model="auto/coding:free",
            privacy_class="INTERNAL_SANITIZED",
        )
        agent_ops = get_task_route("leadgen.agent_ops", "INTERNAL_SANITIZED")
        assert agent_ops.privacy_class == "INTERNAL_SANITIZED"
        assert "leadgen.agent_ops" in {
            "leadgen.coding_primary",
            "leadgen.coding_fast",
            "leadgen.repo_analysis",
            "leadgen.test_generation",
            "leadgen.agent_ops",
            "leadgen.swara_live",
        }

    def test_registry_rejects_customer_and_unknown_routes(self):
        with pytest.raises(SafePayloadError):
            get_task_route("leadgen.customer_report_summary", "CUSTOMER_SANITIZED")
        with pytest.raises(SafePayloadError):
            get_task_route("leadgen.unknown", "INTERNAL_SANITIZED")

    @pytest.mark.asyncio
    async def test_generate_stays_inert_without_explicit_opt_in(self, monkeypatch):
        monkeypatch.delenv("OMNIROUTE_ENABLED", raising=False)
        monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
        assert (
            await generate(
                "leadgen.coding_primary",
                [{"role": "user", "content": "write a test"}],
                "INTERNAL_SANITIZED",
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_generate_uses_responses_api_and_masks_payload(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        seen = {}

        async def fake_post(url, headers, payload, timeout):
            seen.update(url=url, headers=headers, payload=payload, timeout=timeout)
            return _Response(
                payload={
                    "model": "llama-3.3-70b-versatile",
                    "output_text": "safe result",
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                }
            )

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        result = await generate(
            "leadgen.coding_primary",
            [{"role": "user", "content": "Call 9876543210 and write a test"}],
            "INTERNAL_SANITIZED",
        )

        assert result is not None
        assert result.text == "safe result"
        assert result.provider == "combo"  # bare combo id — not faked as a provider
        assert seen["url"].endswith("/v1/responses")
        assert seen["payload"]["model"] == "leadgen-free-first"
        assert "9876543210" not in str(seen["payload"])

    @pytest.mark.asyncio
    async def test_retryable_primary_failure_uses_verified_fallback(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        models = []

        async def fake_post(url, headers, payload, timeout):
            models.append(payload["model"])
            if len(models) == 1:
                return _Response(status_code=429)
            return _Response(
                payload={"model": "mistral-small-latest", "output_text": "fallback ok"}
            )

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        result = await generate(
            "leadgen.coding_primary",
            [{"role": "user", "content": "write a test"}],
            "INTERNAL_SANITIZED",
        )

        assert result is not None
        assert result.text == "fallback ok"
        assert result.fallback_reason == "http_429"
        assert models == ["leadgen-free-first", "auto/coding:free"]

    @pytest.mark.asyncio
    async def test_non_retryable_primary_failure_does_not_fallback(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        attempts = 0

        async def fake_post(url, headers, payload, timeout):
            nonlocal attempts
            attempts += 1
            return _Response(status_code=401)

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        assert (
            await generate(
                "leadgen.coding_primary",
                [{"role": "user", "content": "write a test"}],
                "INTERNAL_SANITIZED",
            )
            is None
        )
        assert attempts == 1


class TestOmniRouteAgentHook:
    """ADR-108: staff-agent opt-in gate — double-gated, sanitized, fail-open."""

    def _clear(self, monkeypatch):
        monkeypatch.delenv("OMNIROUTE_ENABLED", raising=False)
        monkeypatch.delenv("OMNIROUTE_AGENTS", raising=False)
        monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)

    def test_agents_disabled_by_default(self, monkeypatch):
        from app.platform.omniroute_client import agents_enabled

        self._clear(monkeypatch)
        assert agents_enabled() is False

    def test_agents_flag_alone_is_not_enough(self, monkeypatch):
        """OMNIROUTE_AGENTS=1 without master flag+key must stay OFF (double gate)."""
        from app.platform.omniroute_client import agents_enabled

        self._clear(monkeypatch)
        monkeypatch.setenv("OMNIROUTE_AGENTS", "1")
        assert agents_enabled() is False
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")  # still no key
        assert agents_enabled() is False

    def test_agents_enabled_when_fully_gated_open(self, monkeypatch):
        from app.platform.omniroute_client import agents_enabled

        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_AGENTS", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        assert agents_enabled() is True

    @pytest.mark.asyncio
    async def test_try_agent_chat_inert_when_disabled(self, monkeypatch):
        from app.platform.omniroute_client import try_agent_chat

        self._clear(monkeypatch)
        called = False

        async def fake_post(url, headers, payload, timeout):  # pragma: no cover
            nonlocal called
            called = True
            return _Response(payload={"output_text": "should never happen"})

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        assert await try_agent_chat([{"role": "user", "content": "hello"}]) is None
        assert called is False  # zero network attempts while gated OFF

    @pytest.mark.asyncio
    async def test_try_agent_chat_happy_path_masks_payload(self, monkeypatch):
        from app.platform.omniroute_client import try_agent_chat

        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_AGENTS", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        seen = {}

        async def fake_post(url, headers, payload, timeout):
            seen.update(payload=payload)
            return _Response(
                payload={"model": "llama-3.3-70b-versatile", "output_text": "agent ok"}
            )

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        text = await try_agent_chat(
            [{"role": "user", "content": "Summarise leads, call 9876543210 back"}]
        )
        assert text == "agent ok"
        assert seen["payload"]["model"] == "leadgen-free-first"  # leadgen.agent_ops primary (combo)
        assert "9876543210" not in str(seen["payload"])  # customer data masked

    @pytest.mark.asyncio
    async def test_try_agent_chat_never_raises_on_gateway_fault(self, monkeypatch):
        from app.platform.omniroute_client import try_agent_chat

        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_AGENTS", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")

        async def fake_post(url, headers, payload, timeout):
            raise httpx.ConnectError("gateway down")

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        assert await try_agent_chat([{"role": "user", "content": "hello"}]) is None

    @pytest.mark.asyncio
    async def test_zara_agent_ops_still_masks_customer_pii(self, monkeypatch):
        """may_contact_customers=True agents still use INTERNAL_SANITIZED masking."""
        from app.platform.omniroute_client import try_agent_chat

        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_AGENTS", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        seen = {}

        async def fake_post(url, headers, payload, timeout):
            seen["payload"] = payload
            return _Response(
                payload={
                    "model": "groq/llama-3.3-70b-versatile",
                    "output_text": "ok",
                }
            )

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        text = await try_agent_chat(
            [{"role": "user", "content": "Call customer 9876543210 tonight"}],
            agent_key="zara",
        )
        assert text == "ok"
        assert "9876543210" not in str(seen["payload"])

    @pytest.mark.asyncio
    async def test_max_output_tokens_override_and_provider_from_resolved(self, monkeypatch):
        from app.platform.omniroute_client import generate

        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        seen = {}

        async def fake_post(url, headers, payload, timeout):
            seen["payload"] = payload
            return _Response(
                payload={
                    "model": "groq/llama-3.3-70b-versatile",
                    "output_text": "tok ok",
                }
            )

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        result = await generate(
            "leadgen.coding_primary",
            [{"role": "user", "content": "hi"}],
            "INTERNAL_SANITIZED",
            max_output_tokens=256,
        )
        assert result is not None
        assert seen["payload"]["max_output_tokens"] == 256
        assert result.provider == "groq"  # from gateway-resolved model

    @pytest.mark.asyncio
    async def test_free_ai_chat_bulk_uses_hook_and_realtime_never_does(self, monkeypatch):
        """free_ai.chat: bulk profile → omniroute pre-hook; realtime → existing chain only.

        conftest.py suite-wide `free_ai.chat` ko stub karta hai (network-hang guard),
        isliye yahan module ki FRESH isolated copy load karke REAL chat test karte hai
        — sys.modules untouched, baaki suite ka stub intact.
        """
        import importlib.util

        spec = importlib.util.find_spec("app.voice_agent.free_ai")
        free_ai = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(free_ai)

        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_AGENTS", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        calls = []

        async def fake_hook(messages, agent_key=None, product=None):
            calls.append({"messages": messages, "agent_key": agent_key, "product": product})
            return "omni agent reply"

        monkeypatch.setattr("app.platform.omniroute_client.try_agent_chat", fake_hook)
        # Cache OFF for this test — hook se pehle cache-hit na aa jaye.
        monkeypatch.setattr(free_ai, "_llm_cache_on", lambda prof: False)

        text, provider = await free_ai.chat(
            "system",
            [{"role": "user", "content": "write digest"}],
            max_tokens=512,
            profile="bulk",
            agent_key="zara",
            product="marketing",
        )
        assert (text, provider) == ("omni agent reply", "omniroute")
        assert len(calls) == 1
        assert calls[0]["agent_key"] == "zara"
        assert calls[0]["product"] == "marketing"

        # Realtime (voice hot-path) must NEVER touch the hook — chain empty = ("","").
        monkeypatch.setattr(free_ai, "_build_llm_chain", lambda prof: [])
        text2, provider2 = await free_ai.chat(
            "system",
            [{"role": "user", "content": "hello"}],
            max_tokens=60,
            profile="realtime",
        )
        assert len(calls) == 1  # no new hook call
        assert provider2 != "omniroute"

        # Default / non-bulk / non-realtime must ALSO skip hook (ADR bulk-only).
        text3, provider3 = await free_ai.chat(
            "system",
            [{"role": "user", "content": "short"}],
            max_tokens=40,
            profile="default",
        )
        assert len(calls) == 1
        assert provider3 != "omniroute"
