"""ADR-104 (2026-07-15, Priority 6) -- frontend/admin_dashboard.html Customer
360 panel "Deliver Value Now" button had zero confirmation.

c360DeliverNow() called POST /api/admin/clients/{id}/deliver-now directly on
click -> app.api.admin_ops.deliver_now() -> customer_delivery.deliver_client_
value(client, force=True), which sends a REAL WhatsApp message to the
customer's real phone number and bypasses the normal AUTO_DELIVER_VALUE gate.
This is the exact same backend endpoint as frontend/clients.html's "Deliver
Now" button, already fixed in ADR-104 Phase F (commit 5f65979, see
test_clients_page_confirm_modal.py) -- but this second UI surface (the
Customer 360 panel on /app/admin) was never covered by that fix, and was
found-but-not-fixed in this session's Priority 4 admin endpoint audit.

The backend endpoint already writes a delivery_ledger "admin_manual_action"
audit event on every call (success or failure) -- see
tests/test_admin_client_actions_audit.py's deliver-now sibling coverage is
out of scope here; this file only covers the frontend confirmation gap.

admin_dashboard.html has its own in-file modal convention (_focusTrap-based
custom overlay, used by the pre-existing password-reset modal and this
session's Priority 4 Re-Scrape-website modal) rather than clients.html's
actionConfirmModal() helper -- this fix follows that same established
in-file pattern for consistency, not a copy of clients.html's helper.

Same test convention as test_clients_page_confirm_modal.py: pure text/
structure assertions against the shipped HTML/JS (no JS runtime assumed).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "frontend" / "admin_dashboard.html"


def _text() -> str:
    return PAGE.read_text(encoding="utf-8")


def _function_body(text: str, signature: str) -> str:
    """Brace-depth match a function body (indentation-agnostic)."""
    start = text.index(signature)
    brace_start = text.index("{", start)
    depth = 0
    i = brace_start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise AssertionError("unbalanced braces looking for " + signature)


def test_page_exists():
    assert PAGE.exists()


def test_c360delivernow_button_still_wired_to_the_same_function_name():
    t = _text()
    assert 'onclick="c360DeliverNow()"' in t
    assert 'id="c360DeliverBtn"' in t


def test_c360delivernow_no_longer_calls_fetch_directly():
    """Clicking the button must only open the confirmation modal -- no
    network call may happen before the operator explicitly confirms."""
    t = _text()
    body = _function_body(t, "function c360DeliverNow() {")
    assert "fetch(" not in body
    assert "/deliver-now" not in body


def test_c360delivernow_opens_a_modal_with_focus_trap():
    t = _text()
    body = _function_body(t, "function c360DeliverNow() {")
    assert "c360DeliverModalOverlay" in body
    assert "_focusTrap(overlay, _closeC360DeliverModal)" in body
    assert 'role", "dialog"' in body or 'setAttribute("role", "dialog")' in body


def test_modal_copy_states_real_whatsapp_contact_and_names_the_bypassed_gate():
    t = _text()
    body = _function_body(t, "function c360DeliverNow() {")
    assert "real WhatsApp message" in body
    assert "AUTO_DELIVER_VALUE" in body


def test_cancel_and_backdrop_click_close_without_any_network_call():
    t = _text()
    body = _function_body(t, "function c360DeliverNow() {")
    assert 'onclick="_closeC360DeliverModal()"' in body
    close_body = _function_body(t, "function _closeC360DeliverModal() {")
    assert "fetch(" not in close_body


def test_only_the_confirm_button_can_trigger_the_real_api_call():
    t = _text()
    confirmed_body = _function_body(t, "async function _c360DeliverConfirmed() {")
    assert "fetch(" in confirmed_body
    assert "/deliver-now" in confirmed_body
    # The confirm button in the modal markup must call this exact function.
    modal_body = _function_body(t, "function c360DeliverNow() {")
    assert 'onclick="_c360DeliverConfirmed()"' in modal_body


def test_confirmed_handler_closes_modal_before_firing_the_request():
    """The modal must be dismissed (and thus not double-clickable) before
    the real API call is made."""
    t = _text()
    body = _function_body(t, "async function _c360DeliverConfirmed() {")
    close_idx = body.index("_closeC360DeliverModal()")
    fetch_idx = body.index("fetch(")
    assert close_idx < fetch_idx


def test_scrape_modal_pattern_unchanged_regression_guard():
    """Regression guard: the pre-existing Priority-4 Re-Scrape confirmation
    (added earlier this session) must not have been altered by this fix."""
    t = _text()
    body = _function_body(t, "function c360ScrapeWebsite() {")
    assert "fetch(" not in body
    assert "c360ScrapeModalOverlay" in body
