"""SSRF defense tests for website_auditor (alert-autofix-34 coverage).

Tests _normalize_safe_audit_url() hardening:
- Credential rejection (http://user:pass@host)  # pragma: allowlist secret
- Fragment rejection (http://example.com#fragment)
- Private IP blocks (127.0.0.1, 10.x, 192.168.x, 169.254.x)
- localhost / .local / .internal rejection
- Valid public URLs pass through
"""

from __future__ import annotations

import pytest


def test_normalize_safe_audit_url_blocks_private_ips():
    from app.marketing.website_auditor import _normalize_safe_audit_url

    # Loopback
    assert _normalize_safe_audit_url("http://127.0.0.1") is None
    assert _normalize_safe_audit_url("http://localhost") is None
    assert _normalize_safe_audit_url("http://[::1]") is None

    # Private ranges
    assert _normalize_safe_audit_url("http://10.0.0.1") is None
    assert _normalize_safe_audit_url("http://192.168.1.1") is None
    assert _normalize_safe_audit_url("http://172.16.0.1") is None

    # Cloud metadata (AWS/GCP/Azure common)
    assert _normalize_safe_audit_url("http://169.254.169.254") is None
    assert _normalize_safe_audit_url("http://169.254.169.254/latest/meta-data/") is None

    # .local / .internal
    assert _normalize_safe_audit_url("http://service.local") is None
    assert _normalize_safe_audit_url("http://api.internal") is None


def test_normalize_safe_audit_url_blocks_credentials():
    from app.marketing.website_auditor import _normalize_safe_audit_url

    # Basic auth embedded = REJECT (fixture URLs — not real credentials)
    cred_url = "http://user:pass@example.com"  # pragma: allowlist secret
    assert _normalize_safe_audit_url(cred_url) is None
    userinfo_url = "http://admin@example.com"  # pragma: allowlist secret
    assert _normalize_safe_audit_url(userinfo_url) is None
    https_cred = "https://user:pass@public-site.com/path"  # pragma: allowlist secret
    assert _normalize_safe_audit_url(https_cred) is None


def test_normalize_safe_audit_url_blocks_fragments():
    from app.marketing.website_auditor import _normalize_safe_audit_url

    # Fragments can cause parser confusion in some libraries
    assert _normalize_safe_audit_url("http://example.com#fragment") is None
    assert _normalize_safe_audit_url("https://site.com/path#anchor") is None


def test_normalize_safe_audit_url_rejects_malformed():
    from app.marketing.website_auditor import _normalize_safe_audit_url

    # No scheme
    assert _normalize_safe_audit_url("example.com") is None

    # Bad scheme
    assert _normalize_safe_audit_url("ftp://example.com") is None
    assert _normalize_safe_audit_url("file:///etc/passwd") is None

    # Empty / whitespace
    assert _normalize_safe_audit_url("") is None
    assert _normalize_safe_audit_url("   ") is None

    # No hostname
    assert _normalize_safe_audit_url("http://") is None


def test_normalize_safe_audit_url_accepts_valid_public(monkeypatch):
    import socket

    from app.marketing.website_auditor import _normalize_safe_audit_url

    # Mock DNS resolution to return a public IP
    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host in ("example.com", "www.google.com"):
            # Return a public IP (93.184.216.34 for example.com)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]
        raise socket.gaierror("Mock DNS: host not found")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # Valid public URLs should pass (assert via urlparse — avoids CodeQL
    # py/incomplete-url-substring-sanitization on startswith/full-URL checks)
    from urllib.parse import urlparse

    result = _normalize_safe_audit_url("http://example.com")
    assert result is not None
    parsed = urlparse(result)
    assert parsed.scheme == "http"
    assert parsed.hostname == "example.com"

    result = _normalize_safe_audit_url("https://www.google.com/test")
    assert result is not None
    parsed = urlparse(result)
    assert parsed.scheme == "https"
    assert parsed.hostname == "www.google.com"

    # Canonical form
    result = _normalize_safe_audit_url("  https://example.com/path?q=1  ")
    assert result == "https://example.com/path?q=1"


def test_safe_audit_target_legacy_function_still_works(monkeypatch):
    """Ensure legacy _safe_audit_target() still works (not removed)."""
    import socket

    from app.marketing.website_auditor import _safe_audit_target

    # Mock DNS resolution
    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]
        raise socket.gaierror("Mock DNS: host not found")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    assert _safe_audit_target("http://example.com") is True
    assert _safe_audit_target("http://127.0.0.1") is False
    assert _safe_audit_target("http://192.168.1.1") is False


@pytest.mark.asyncio
async def test_audit_url_rejects_ssrf_attempts():
    """Integration: audit_url() rejects SSRF vectors early."""
    from app.marketing.website_auditor import audit_url

    # Private IP
    result = await audit_url("http://127.0.0.1")
    assert result["ok"] is False
    assert "allowed nahi" in result["error"].lower()

    result = await audit_url("http://169.254.169.254/latest/meta-data/")
    assert result["ok"] is False

    # Credentials
    result = await audit_url("http://admin:pass@example.com")  # pragma: allowlist secret
    assert result["ok"] is False

    # Fragment
    result = await audit_url("http://example.com#fragment")
    assert result["ok"] is False


def test_resolve_is_public_function_coverage(monkeypatch):
    """_resolve_is_public() helper coverage (SSRF core logic)."""
    import socket

    from app.marketing.website_auditor import _resolve_is_public

    # Mock DNS resolution
    def mock_getaddrinfo(host, port, *args, **kwargs):
        host_lower = (host or "").lower().strip().rstrip(".")
        if host_lower in ("example.com", "google.com"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]
        if host_lower == "localhost":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        if host_lower.endswith((".local", ".internal")):
            raise socket.gaierror("No address associated with hostname")
        raise socket.gaierror("Mock DNS: host not found")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # Public: example.com, google.com (mocked as public IPs)
    assert _resolve_is_public("example.com") is True
    assert _resolve_is_public("google.com") is True

    # Private: localhost, .local
    assert _resolve_is_public("localhost") is False
    assert _resolve_is_public("test.local") is False
    assert _resolve_is_public("api.internal") is False

    # Nonexistent domain
    assert _resolve_is_public("nonexistent-xyz-12345.invalid") is False

    # Empty
    assert _resolve_is_public("") is False
