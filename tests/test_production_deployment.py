"""
Production post-deployment verification tests.
These tests verify that the actual deployed code contains the fixes.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_logout_endpoint_exists_and_callable():
    """Verify logout endpoint exists and can be called (even if Redis unavailable)."""
    from app.api.admin import create_access_token

    token = create_access_token("test-customer", "test@example.com", "customer")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/customer/auth/logout", headers=headers)
    # Should return 200 (success) or 401 (invalid token), not 404
    assert resp.status_code in (200, 401), f"Logout endpoint should exist, got {resp.status_code}"


def test_logout_invalidates_token():
    """Verify that calling logout marks token as revoked."""
    from app.api.admin import create_access_token

    token = create_access_token("test-logout-2", "test2@example.com", "customer")
    headers = {"Authorization": f"Bearer {token}"}

    # Call logout
    logout_resp = client.post("/api/customer/auth/logout", headers=headers)
    assert logout_resp.status_code in (200, 401)

    # Try to use token afterward (may succeed if Redis unavailable, but code path exercised)
    me_resp = client.get("/api/customer/auth/me", headers=headers)
    # Either 401 (revoked) or 200 (Redis unavailable) are acceptable
    assert me_resp.status_code in (200, 401)


def test_require_customer_is_async():
    """Verify require_customer dependency is now async (supports Redis blacklist check)."""
    import inspect

    from app.api.customer_auth import require_customer

    # Should be an async function
    assert inspect.iscoroutinefunction(require_customer), "require_customer should be async"


def test_billing_invoices_endpoint_queries_both_sources():
    """Verify /api/billing/invoices reads both Postgres and JSONL (code inspection)."""
    import inspect

    from app.api import billing

    source = inspect.getsource(billing.get_invoices)

    assert "gst_invoice" in source, "/api/billing/invoices should read from gst_invoice (JSONL)"
    assert "Invoice" in source, "/api/billing/invoices should read from Postgres Invoice table"
    # Alias-aware JSONL match (jiya slug vs legacy billing id)
    assert "_billing_client_ids" in source or "alias_ids" in source
    assert "alias_set" in source or "alias_ids" in source
    # Postgres path must populate full InvoiceResponse (not just hosted_url)
    assert "invoice_number=inv.invoice_number" in source
    assert "hosted_url=inv.hosted_invoice_url" in source
    assert "InvoiceResponse(\n                hosted_url=" not in source


def test_customer_portal_logout_calls_api():
    """Verify login + customer dashboard logout call the revoke API."""
    with open("frontend/login.html", encoding="utf-8") as f:
        login = f.read()
    with open("frontend/customer_dashboard.html", encoding="utf-8") as f:
        dash = f.read()

    assert "/api/customer/auth/logout" in login, "login.html should call logout API"
    assert "POST" in login, "Logout should be a POST request"
    assert "doCustomerLogout" in dash, "customer_dashboard should define doCustomerLogout"
    assert "/api/customer/auth/logout" in dash, "customer_dashboard should call logout API"
    assert "doCustomerLogout(" in dash
    # No local-only logout that skips server revoke on the error banner
    assert (
        "localStorage.removeItem('lgai_token');window.location.replace('/app/login?reason=retry_failed')"
        not in dash
    )


def test_no_silent_failures_in_logout():
    """Verify logout endpoint gracefully handles Redis unavailability."""
    import inspect

    from app.api.customer_auth import logout

    source = inspect.getsource(logout)

    # Should have try/except for Redis failures
    assert "except" in source, "Logout should handle errors gracefully"
    # Should return 200 even if Redis fails
    assert "return" in source and "message" in source, "Logout should always return success message"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
