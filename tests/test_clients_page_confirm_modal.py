"""ADR-104 Phase F (2026-07-15) -- frontend/clients.html unconfirmed
approve/post/skip actions (3rd instance of the same bug family this session).

Live discovery during the Phase F admin walkthrough: /app/clients (the
customer content queue -- where Jiya Makeover Studio's real pending draft
content is shown) called markItem() directly from each Approve/Posted/Skip
button's onclick, firing POST /api/clients/{id}/content/{itemId}/status with
NO confirmation step at all -- not even a native confirm(), which is a worse
gap than the two surfaces already fixed this session (frontend/automation.html,
frontend/delivery_command_center.html -- see test_action_confirm_modal.py).

Note this action is lower blast-radius than the other two: mark_item()
(app/marketing/auto_content.py) only rewrites a local JSONL bookkeeping
status -- it does not itself trigger a public post (auto-posting is still a
separate manual copy/download step per CLAUDE.md). The modal's copy reflects
that accurately ("record", never "publish"). Still gated because mislabeling
a real customer's content (approved/posted/skipped) with a stray click is a
real mistake this page had zero protection against.

Same test convention as test_action_confirm_modal.py: pure text/structure
assertions against the shipped HTML/JS (no JS runtime assumed on PATH).

Follow-up same file, same walkthrough: the "Deliver Now" button on this same
page's Delivery Timeline panel (deliverNow() -> POST /api/admin/clients/{id}/
deliver-now -> customer_delivery.deliver_client_value(client, force=True)) is
a REAL forced delivery to a real paid customer that bypasses normal delivery
gating -- the highest-severity unconfirmed action found this session -- and
also had zero confirmation. The modal was extended with a `dangerous` variant
(red, "WILL attempt to actually deliver/contact this real customer") reusing
the same actionConfirmModal, rather than duplicating a second modal.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "frontend" / "clients.html"


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


def test_action_confirm_modal_defined():
    t = _text()
    assert "function actionConfirmModal(opts)" in t


def _modal_body(t: str) -> str:
    return _function_body(t, "function actionConfirmModal(opts){")


def test_modal_returns_a_promise_not_a_synchronous_value():
    body = _modal_body(_text())
    assert "return new Promise(function(resolve)" in body


def test_modal_never_resolves_on_enter_key():
    body = _modal_body(_text())
    assert "'Enter'" not in body and '"Enter"' not in body
    assert "e.key === 'Escape'" in body
    assert "cleanup(false)" in body


def test_modal_only_resolves_true_from_the_explicit_confirm_button_click():
    body = _modal_body(_text())
    assert body.count("cleanup(true)") == 1
    confirm_click_idx = body.index('data-testid="acm-confirm"]\').onclick')
    cleanup_true_idx = body.index("cleanup(true)")
    assert confirm_click_idx < cleanup_true_idx < confirm_click_idx + 80


def test_opening_the_modal_makes_no_network_call():
    body = _modal_body(_text())
    assert "callApi(" not in body
    assert "fetch(" not in body


def test_modal_states_this_is_not_a_public_post():
    """Accuracy guard: mark_item() only changes an internal bookkeeping
    status, so the modal copy must never claim a public/live post here
    (that claim belongs only to automation.html/delivery_command_center.html's
    modal, which gates genuinely public-facing actions)."""
    body = _modal_body(_text())
    assert "does NOT post publicly" in body
    assert "WILL post publicly" not in body


def test_data_act_click_handler_gated_by_modal_before_markitem():
    t = _text()
    body = _function_body(t, "function renderItems(c){")
    modal_idx = body.index("actionConfirmModal(")
    guard_idx = body.index("if(!ok) return")
    markitem_idx = body.index("markItem(c, rec.id, act, b)")
    assert modal_idx < guard_idx < markitem_idx


def test_click_handler_is_async():
    t = _text()
    body = _function_body(t, "function renderItems(c){")
    assert "b.onclick = async function()" in body


def test_action_labels_are_per_status_and_accurate():
    t = _text()
    assert "ACT_LABEL" in t
    assert "approved:" in t
    assert "posted:" in t
    assert "skipped:" in t
    # "posted" here must read as a record of a manual share, never a live
    # auto-post claim (mark_item() has no such side effect).
    idx = t.index("posted:")
    line = t[idx : t.index("\n", idx)]
    assert "already posted" in line or "manually shared" in line


def test_modal_receives_client_and_content_context():
    t = _text()
    body = _function_body(t, "function renderItems(c){")
    assert "c.business_name" in body
    assert "titleForModal" in body


# --------------------------------------------------------------------------- #
# "Deliver Now" (deliverNow()) -- highest-severity unconfirmed action found
# this session: a REAL forced delivery to a real paid customer, bypassing
# normal gating, that had zero confirmation before this fix.
# --------------------------------------------------------------------------- #


def test_modal_supports_a_dangerous_variant_for_real_customer_contact():
    t = _text()
    body = _modal_body(t)
    assert "opts.dangerous" in body
    assert "WILL attempt to actually deliver/contact this real customer" in body


def test_delivernow_gated_by_modal_before_its_api_call():
    t = _text()
    body = _function_body(t, "async function deliverNow(c){")
    modal_idx = body.index("actionConfirmModal(")
    dangerous_idx = body.index("dangerous: true")
    guard_idx = body.index("if(!ok) return")
    api_idx = body.index('callApi("/api/admin/clients/')
    assert modal_idx < dangerous_idx < guard_idx < api_idx


def test_delivernow_modal_call_passes_customer_name():
    t = _text()
    body = _function_body(t, "async function deliverNow(c){")
    assert "customer: c.business_name || c.id" in body
