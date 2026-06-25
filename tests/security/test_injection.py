"""Security tests — Injection.

Verifies that SQL injection, XSS, and command injection vectors are blocked
or mitigated across the API surface.

Playbook ref: Security Playbook — Injection tests.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)

# Common SQL injection payloads
SQLI_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "1 UNION SELECT * FROM users",
    "1; INSERT INTO users VALUES ('hacker','pass')",
    "' OR '1'='1' /*",
]

# Common XSS payloads
XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert('xss')>",
    "javascript:alert('xss')",
    "<body onload=alert('xss')>",
]


# ---------------------------------------------------------------------------
# SQL Injection — public search/audit endpoints
# ---------------------------------------------------------------------------
def test_public_search_rejects_sqli():
    """Public search endpoints must sanitize or reject SQL injection payloads."""
    for payload in SQLI_PAYLOADS:
        resp = client.get(f"/api/public/search?q={payload}", follow_redirects=False)
        # We expect 200 (if sanitized) or 400/422 (if rejected) — NOT 500.
        assert resp.status_code != 500, (
            f"SQLi payload caused 500: {payload[:50]}..."
        )


def test_audit_endpoint_rejects_sqli():
    """Audit endpoint must not crash on SQLi payloads in URL params."""
    for payload in SQLI_PAYLOADS:
        resp = client.get(f"/api/audit?url={payload}", follow_redirects=False)
        assert resp.status_code != 500, (
            f"SQLi payload caused 500 on /api/audit: {payload[:50]}..."
        )


# ---------------------------------------------------------------------------
# SQL Injection — customer mutation endpoints
# ---------------------------------------------------------------------------
def test_customer_profile_rejects_sqli():
    """Customer profile fields must reject SQL injection."""
    for payload in SQLI_PAYLOADS:
        resp = client.post(
            "/api/customer/onboard",
            json={"name": payload, "phone": "9999999999", "business": payload},
            follow_redirects=False,
        )
        assert resp.status_code != 500, (
            f"SQLi payload caused 500 in onboard: {payload[:50]}..."
        )


# ---------------------------------------------------------------------------
# XSS — output encoding
# ---------------------------------------------------------------------------
def test_public_endpoints_encode_xss():
    """If an endpoint echoes user input, it must be HTML-escaped."""
    for payload in XSS_PAYLOADS:
        resp = client.get(f"/api/public/search?q={payload}", follow_redirects=False)
        if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
            body = resp.text
            assert payload not in body, (
                f"XSS payload echoed unescaped: {payload[:50]}..."
            )


# ---------------------------------------------------------------------------
# Command injection — voice/telephony params (if any shell exec)
# ---------------------------------------------------------------------------
CMDI_PAYLOADS = [
    "; cat /etc/passwd",
    "| whoami",
    "$(id)",
    "`uname -a`",
    "&& ls -la",
]


def test_telephony_params_reject_cmdi():
    """Telephony endpoints must not pass user input to shell execution."""
    for payload in CMDI_PAYLOADS:
        resp = client.post(
            "/api/telephony/call",
            json={"to": f"+91{payload}", "message": payload},
            follow_redirects=False,
        )
        assert resp.status_code in (401, 403, 422, 400), (
            f"Command injection payload not rejected: {payload[:50]}..."
        )


# ---------------------------------------------------------------------------
# Path traversal — file upload / static paths
# ---------------------------------------------------------------------------
PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..\\..\\..\\windows\\system32\\config\\sam",
    "....//....//etc/passwd",
]


def test_file_paths_reject_traversal():
    """Static/download endpoints must not serve files outside intended directory."""
    for payload in PATH_TRAVERSAL_PAYLOADS:
        resp = client.get(f"/data/{payload}", follow_redirects=False)
        assert resp.status_code in (404, 403, 400), (
            f"Path traversal not blocked: {payload[:50]}..."
        )
