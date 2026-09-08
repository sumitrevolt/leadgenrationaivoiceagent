"""Test the free_ai._blocked_for_provider defense-in-depth gate (Phase 6, OmniRoute
audit 2026-07-12). Synthetic data only — no real customer PII.

This covers the actual call-site wiring added to app/voice_agent/free_ai.py
(chat, chat_stream, chat_provider, gemini_vertex branch), on top of the existing
unit tests in tests/test_safe_ai_payload.py which test block_if_sensitive() directly.
"""

from app.voice_agent.free_ai import _blocked_for_provider


class TestBlockedForProvider:
    def test_unsafe_provider_with_synthetic_phone_is_blocked(self):
        msgs = [{"role": "user", "content": "call this customer"}]
        # Deliberately bypass masking to prove the defense-in-depth layer alone works.
        raw = [{"role": "user", "content": "phone 9876543210 email test@example.com"}]
        assert _blocked_for_provider(raw, "deepseek") is True
        assert _blocked_for_provider(raw, "qwen") is True
        assert _blocked_for_provider(raw, "glm") is True
        assert _blocked_for_provider(raw, "kimi") is True

    def test_unsafe_provider_with_synthetic_api_key_string_is_blocked(self):
        raw = [{"role": "user", "content": "api_key = sk-fakeTestKey1234567890"}]
        assert _blocked_for_provider(raw, "groq") is True  # strict tier: secrets blocked

    def test_normal_coding_prompt_passes_through(self):
        clean = [{"role": "user", "content": "write a python function to sort a list"}]
        assert _blocked_for_provider(clean, "deepseek") is False
        assert _blocked_for_provider(clean, "groq") is False
        assert _blocked_for_provider(clean, "claude") is False

    def test_claude_trusted_tier_never_blocked_even_with_names(self):
        msgs = [{"role": "user", "content": "customer name is Rahul, review this code"}]
        assert _blocked_for_provider(msgs, "claude") is False

    def test_malformed_input_fails_open_not_closed(self):
        # An unrelated crash in the gate must never take down the whole chat path.
        assert _blocked_for_provider(object(), "deepseek") is False
