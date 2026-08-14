from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUSTOMER = (ROOT / "frontend" / "customer_dashboard.html").read_text(encoding="utf-8")
ADMIN = (ROOT / "frontend" / "admin_dashboard.html").read_text(encoding="utf-8")
ADMIN_API = (ROOT / "app" / "api" / "admin_ops.py").read_text(encoding="utf-8")


def test_setup_review_cta_has_explicit_seed_button_contract():
    assert 'onclick="generateFirstWeek(this)"' in CUSTOMER
    assert "function generateFirstWeek(btnEl)" in CUSTOMER
    assert 'document.getElementById("swSeedBtn")' in CUSTOMER


def test_customer_identity_never_uses_url_client_id_fallback():
    assert 'qparam("client_id")' not in CUSTOMER
    assert 'return localStorage.getItem("lgai_cid") || "demo";' not in CUSTOMER
    assert 'window.location.replace("/app/login?next="' in CUSTOMER


def test_webhook_metadata_and_delivery_errors_are_auth_honest():
    assert 'fetch("/api/customer/webhooks/_meta", {headers: billAuthHdr()})' in CUSTOMER
    assert "if(!r.ok)" in CUSTOMER
    assert "Session expired" in CUSTOMER
    assert "No deliveries yet." in CUSTOMER


def test_pending_approvals_have_customer_visible_notification_cta():
    assert "pending approvals" in CUSTOMER.lower()
    assert "deliveryApprovalSection" in CUSTOMER
    assert "showView('delivery')" in CUSTOMER or 'showView("delivery")' in CUSTOMER


def test_platform_dial_is_backend_bound_and_campaign_button_is_safe():
    assert 'id="platformDialBanner"' in ADMIN
    assert "sys.platform_dial" in ADMIN
    assert '"platform_dial": {' in ADMIN_API
    assert "campFireBtn" in ADMIN
    assert "disabled" in ADMIN


def test_bulk_delete_reports_partial_failures_and_keeps_selection():
    assert "failed" in ADMIN
    assert "Deleting" in ADMIN
    assert "if(failed)" in ADMIN
    assert "clearBulkSelect()" in ADMIN


def test_dead_upi_billing_portal_function_is_removed():
    assert "async function openBillingPortal" not in CUSTOMER


def test_god_mode_success_paths_use_admin_toast():
    assert "alert('✅ Turnstile armed')" not in ADMIN
    assert "alert('✅ Sentry saved" not in ADMIN
    assert "alert('✅ PostHog saved')" not in ADMIN
    assert "alert('✅ UPI VPA save" not in ADMIN


def test_marketing_suite_has_today_start_here():
    html = (ROOT / "frontend" / "marketing.html").read_text(encoding="utf-8")
    assert 'id="mktStartHere"' in html
    assert 'href="/app/inbox"' in html
    assert "Aaj kya karna hai" in html
