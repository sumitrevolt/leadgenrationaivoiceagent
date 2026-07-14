"""Test app/platform/omniroute_client.py — must stay fully INERT by default.

Audit 2026-07-12. Sumit's OmniRoute instance has no admin auth configured, so this
module must never attempt a real network call unless explicitly enabled+keyed.
"""
import httpx
import pytest

from app.platform.omniroute_client import (
    OmniRouteRoute,
    get_task_route,
    generate,
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
        assert route == OmniRouteRoute(
            primary_model="groq/llama-3.3-70b-versatile",
            fallback_model="mistral/mistral-small-latest",
            privacy_class="INTERNAL_SANITIZED",
        )

    def test_registry_rejects_customer_and_unknown_routes(self):
        with pytest.raises(SafePayloadError):
            get_task_route("leadgen.customer_report_summary", "CUSTOMER_SANITIZED")
        with pytest.raises(SafePayloadError):
            get_task_route("leadgen.unknown", "INTERNAL_SANITIZED")

    @pytest.mark.asyncio
    async def test_generate_stays_inert_without_explicit_opt_in(self, monkeypatch):
        monkeypatch.delenv("OMNIROUTE_ENABLED", raising=False)
        monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
        assert await generate(
            "leadgen.coding_primary", [{"role": "user", "content": "write a test"}],
            "INTERNAL_SANITIZED",
        ) is None

    @pytest.mark.asyncio
    async def test_generate_uses_responses_api_and_masks_payload(self, monkeypatch):
        monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
        monkeypatch.setenv("OMNIROUTE_API_KEY", "synthetic-test-key-not-real")
        seen = {}

        async def fake_post(url, headers, payload, timeout):
            seen.update(url=url, headers=headers, payload=payload, timeout=timeout)
            return _Response(payload={
                "model": "llama-3.3-70b-versatile",
                "output_text": "safe result",
                "usage": {"input_tokens": 3, "output_tokens": 2},
            })

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        result = await generate(
            "leadgen.coding_primary",
            [{"role": "user", "content": "Call 9876543210 and write a test"}],
            "INTERNAL_SANITIZED",
        )

        assert result is not None
        assert result.text == "safe result"
        assert result.provider == "groq"
        assert seen["url"].endswith("/v1/responses")
        assert seen["payload"]["model"] == "groq/llama-3.3-70b-versatile"
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
            return _Response(payload={"model": "mistral-small-latest", "output_text": "fallback ok"})

        monkeypatch.setattr("app.platform.omniroute_client._post_responses", fake_post)
        result = await generate(
            "leadgen.coding_primary", [{"role": "user", "content": "write a test"}],
            "INTERNAL_SANITIZED",
        )

        assert result is not None
        assert result.text == "fallback ok"
        assert result.fallback_reason == "http_429"
        assert models == ["groq/llama-3.3-70b-versatile", "mistral/mistral-small-latest"]

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
        assert await generate(
            "leadgen.coding_primary", [{"role": "user", "content": "write a test"}],
            "INTERNAL_SANITIZED",
        ) is None
        assert attempts == 1
