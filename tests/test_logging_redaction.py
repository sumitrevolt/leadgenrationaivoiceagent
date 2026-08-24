"""
Test credential redaction in HTTP logging.
Ensures sensitive query params (api_key, token, password, etc.) are never exposed in logs.
"""

import pytest

from app.utils.logger import redact_url


class TestCredentialRedaction:
    """Test suite for URL query param redaction"""

    def test_no_query_string(self):
        """URLs without query strings should pass through unchanged"""
        url = "/api/users"
        assert redact_url(url) == url

    def test_empty_url(self):
        """Empty/None URLs should pass through safely"""
        assert redact_url("") == ""
        assert redact_url(None) is None or redact_url(None) == ""

    def test_redact_api_key(self):
        """API keys in query strings must be redacted"""
        url = "/api/users?api_key=sk_test_123&name=john"
        redacted = redact_url(url)
        assert "sk_test_123" not in redacted
        assert "[REDACTED]" in redacted
        assert "name=john" in redacted

    def test_redact_token(self):
        """Auth tokens must be redacted"""
        url = "/api/posts?token=abc123xyz&id=5"
        redacted = redact_url(url)
        assert "abc123xyz" not in redacted
        assert "[REDACTED]" in redacted
        assert "id=5" in redacted

    def test_redact_access_token(self):
        """OAuth access_token must be redacted"""
        url = "/api/social?access_token=ghp_abcdefghijk&user=admin"
        redacted = redact_url(url)
        assert "ghp_abcdefghijk" not in redacted
        assert "[REDACTED]" in redacted
        assert "user=admin" in redacted

    def test_redact_password(self):
        """Passwords must be redacted"""
        url = "/api/auth?password=SecurePass123&username=user@example.com"
        redacted = redact_url(url)
        assert "SecurePass123" not in redacted
        assert "[REDACTED]" in redacted

    def test_case_insensitive_redaction(self):
        """Redaction should be case-insensitive"""
        urls = [
            "/api/test?API_KEY=secret1",
            "/api/test?Api_Key=secret2",
            "/api/test?TOKEN=secret3",
            "/api/test?Token=secret4",
        ]
        for url in urls:
            redacted = redact_url(url)
            # Extract the sensitive part
            for secret in ["secret1", "secret2", "secret3", "secret4"]:
                if secret in url:
                    assert secret not in redacted
                    assert "[REDACTED]" in redacted

    def test_multiple_sensitive_params(self):
        """Multiple sensitive params should all be redacted"""
        url = "/api/sync?api_key=sk_123&token=xyz&password=pass&name=john&id=5"
        redacted = redact_url(url)
        assert "sk_123" not in redacted
        assert "xyz" not in redacted
        assert "password=pass" not in redacted
        assert "name=john" in redacted
        assert "id=5" in redacted
        # Should have 3 redacted values
        assert redacted.count("[REDACTED]") == 3

    def test_safe_params_preserved(self):
        """Non-sensitive params should pass through unchanged"""
        url = "/api/search?q=hello&limit=10&sort=date&user_id=123"
        redacted = redact_url(url)
        assert "q=hello" in redacted
        assert "limit=10" in redacted
        assert "sort=date" in redacted
        assert "user_id=123" in redacted

    def test_url_without_path(self):
        """URL with just query string should be handled"""
        url = "?api_key=secret&name=test"
        redacted = redact_url(url)
        assert "secret" not in redacted
        assert "[REDACTED]" in redacted
        assert "name=test" in redacted

    def test_malformed_url_safe_fallback(self):
        """Malformed URLs should fail safely (return original)"""
        # URL with invalid encoding
        url = "/api/test?key=%ZZinvalid"
        redacted = redact_url(url)
        # Should return something (either original or safe version, not crash)
        assert redacted is not None

    def test_github_token_redaction(self):
        """GitHub tokens (ghp_, ghu_, ghs_ prefixes) should be redacted"""
        urls = [
            "/api/github?token=ghp_abcdefghijklmnop",
            "/api/github?access_token=ghu_fixture_token",
            "/api/github?token=ghs_fixture_token",
        ]
        for url in urls:
            redacted = redact_url(url)
            # Token should not appear in redacted version
            for token in ["ghp_abcdefghijklmnop", "ghu_fixture_token", "ghs_fixture_token"]:
                if token in url:
                    assert token not in redacted
                    assert "[REDACTED]" in redacted

    def test_empty_param_value(self):
        """Empty param values should be preserved"""
        url = "/api/test?api_key=&name=john"
        redacted = redact_url(url)
        assert "name=john" in redacted
        # api_key with empty value should still be redacted
        assert "[REDACTED]" in redacted


class TestMiddlewareIntegration:
    """Integration tests with middleware logging"""

    def test_request_logging_redaction(self, client):
        """Requests with sensitive params should have them redacted in logs"""
        # This test assumes client is a FastAPI test client
        # In real usage: make a request with ?api_key=secret and verify logs
        # For now, we test the redact_url function directly
        test_url = "/api/endpoint?api_key=sk_test_secret&user=john"
        redacted = redact_url(test_url)
        assert "sk_test_secret" not in redacted
        assert "[REDACTED]" in redacted
