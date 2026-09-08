"""ADR-104 (2026-07-15) — in-page confirmation modal for approval/publish/
scheduling/delivery actions, replacing native confirm()/prompt()-only gating.

Background: a native confirm() dialog was proven THIS SESSION to auto-accept
in a browser-automation context before a permission interceptor could block
it -- silently approving a real Jiya Makeover Studio content item. The user's
required fix: replace confirm() with an in-page modal that (a) clearly shows
customer/content/action/channel/connection-state/public-impact, (b) only ever
resolves via an explicit second click inside the page, (c) is never resolved
by Enter, browser-automation defaults, or page load, and (d) must never send
an approval/publish request merely by being opened.

No JS test runner is assumed to be on PATH (same constraint as
test_deploy_vps_retention.py / test_delivery_cockpit_dlq_truth.py), so these
are pure text/structure assertions against the shipped HTML/JS.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTOMATION = REPO_ROOT / "frontend" / "automation.html"
DELIVERY = REPO_ROOT / "frontend" / "delivery_command_center.html"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_line_comments(body: str) -> str:
    """Drop `// ...` line-comment text (which legitimately mentions the word
    "confirm(" while documenting the fix) before asserting no *live* call to
    the native confirm() remains."""
    return "\n".join(
        line if "//" not in line else line[: line.index("//")] for line in body.splitlines()
    )


def _function_body(text: str, signature: str) -> str:
    """Extract a function body by brace-matching from `signature`'s opening
    `{` to its corresponding closing `}` -- indentation-agnostic, since
    automation.html's <script> is 0-indented while delivery_command_center.html's
    is indented by 2 spaces."""
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


# ---------------------------------------------------------------------------
# actionConfirmModal itself must exist in both admin surfaces that perform
# approval/publish/delivery actions.
# ---------------------------------------------------------------------------


def test_pages_exist():
    assert AUTOMATION.exists()
    assert DELIVERY.exists()


def test_action_confirm_modal_defined_in_automation_page():
    t = _text(AUTOMATION)
    assert "function actionConfirmModal(opts)" in t


def test_action_confirm_modal_defined_in_delivery_cockpit_page():
    t = _text(DELIVERY)
    assert "function actionConfirmModal(opts)" in t


def _modal_body(text: str) -> str:
    return _function_body(text, "function actionConfirmModal(opts){")


def test_modal_returns_a_promise_not_a_synchronous_value():
    for text in (_text(AUTOMATION), _text(DELIVERY)):
        body = _modal_body(text)
        assert "return new Promise(function(resolve)" in body


def test_modal_shows_all_required_fields():
    """User spec: customer; content title; action; target channel; internal
    vs public; whether a channel is connected; irreversible/public impact."""
    for text in (_text(AUTOMATION), _text(DELIVERY)):
        body = _modal_body(text)
        assert "opts.customer" in body
        assert "opts.contentTitle" in body
        assert "opts.action" in body
        assert "opts.channel" in body
        assert "opts.channelConnected" in body
        assert "isPublic" in body
        assert "This WILL post publicly" in body
        assert "does NOT post publicly" in body


def test_modal_never_resolves_on_enter_key():
    """Hard requirement: Enter-key must never auto-confirm. Only Escape is
    wired, and it always resolves false (cancel)."""
    for text in (_text(AUTOMATION), _text(DELIVERY)):
        body = _modal_body(text)
        assert "'Enter'" not in body and '"Enter"' not in body
        assert "e.key === 'Escape'" in body or 'e.key === "Escape"' in body
        assert "cleanup(false)" in body


def test_modal_only_resolves_true_from_the_explicit_confirm_button_click():
    """resolve(true) must only be reachable via cleanup(true), and cleanup(true)
    must only be wired to the acm-confirm button's own onclick -- not to
    keydown, not to the overlay/backdrop click, not to modal construction."""
    for text in (_text(AUTOMATION), _text(DELIVERY)):
        body = _modal_body(text)
        assert body.count("cleanup(true)") == 1
        # The querySelector wiring line is the distinctive occurrence -- the
        # button's own data-testid attribute (inside the innerHTML string)
        # also contains "acm-confirm" but has no ".onclick" immediately after it.
        confirm_click_idx = body.index('data-testid="acm-confirm"]\').onclick')
        cleanup_true_idx = body.index("cleanup(true)")
        # cleanup(true) must be wired immediately after (same statement as)
        # the confirm button's own onclick assignment, not earlier in the
        # body (keydown/backdrop/cancel handlers all appear before it and
        # all resolve false).
        assert confirm_click_idx < cleanup_true_idx < confirm_click_idx + 80


def test_opening_the_modal_makes_no_network_call():
    """Constructing/appending the modal DOM must not itself call the page's
    api()/callApi()/fetch() helpers -- only the caller's post-await code
    (gated on the resolved boolean) may do that."""
    for text in (_text(AUTOMATION), _text(DELIVERY)):
        body = _modal_body(text)
        assert "api(" not in body
        assert "callApi(" not in body
        assert "fetch(" not in body


# ---------------------------------------------------------------------------
# Call sites: every approval/publish/delivery action that used to call a bare
# confirm()/prompt() must now await actionConfirmModal(...) and bail out
# before making its network request when the user does not explicitly confirm.
# ---------------------------------------------------------------------------


def _assert_gated_call_site(body: str, guard_var: str, network_marker: str):
    modal_call_idx = body.index("actionConfirmModal(")
    guard_idx = body.index(f"if(!{guard_var}) return")
    network_idx = body.index(network_marker)
    assert modal_call_idx < guard_idx < network_idx


def test_coap_decide_gated_by_modal_before_api_call():
    t = _text(AUTOMATION)
    body = _function_body(t, "async function coApDecide(id,action,clientId,title){")
    assert "confirm(" not in _strip_line_comments(body)  # native confirm() fully removed here
    _assert_gated_call_site(body, "ok", "api('/api/clientops/approvals/")


def test_apcontent_decide_gated_by_modal_before_api_call():
    t = _text(AUTOMATION)
    body = _function_body(t, "async function apContentDecide(id,action,clientId,title){")
    assert "confirm(" not in _strip_line_comments(body)  # native confirm() fully removed here
    _assert_gated_call_site(body, "ok", "api('/api/clientops/approvals/")


def test_delivery_action_approve_pending_gated_by_modal():
    t = _text(DELIVERY)
    body = _function_body(t, "async function deliveryAction(cid, action, customerName){")
    _assert_gated_call_site(body, "okApprove", 'callApi("/api/admin/clients/')


def test_delivery_action_publish_manual_gated_by_modal_before_prompt_and_api():
    t = _text(DELIVERY)
    body = _function_body(t, "async function deliveryAction(cid, action, customerName){")
    # There are two actionConfirmModal(...) calls in this function (one per
    # branch); the publish_manual branch's own call is the second one.
    first_modal_idx = body.index("actionConfirmModal(")
    second_modal_idx = body.index("actionConfirmModal(", first_modal_idx + 1)
    guard_idx = body.index("if(!okPublish) return")
    prompt_idx = body.index('prompt("Manual proof note')
    api_idx = body.index('callApi("/api/admin/clients/')
    assert second_modal_idx < guard_idx < prompt_idx < api_idx


def test_row_render_passes_customer_context_into_gated_actions():
    """The modal is only useful if it actually receives the customer/content
    context to display -- verify the button wiring threads clientId/title
    (automation.html) and customerName (delivery cockpit) through."""
    auto = _text(AUTOMATION)
    assert "coApDecide(" in auto and "cid2" in auto
    assert "apContentDecide(" in auto

    deliv = _text(DELIVERY)
    assert "'approve_pending'" in deliv or '"approve_pending"' in deliv
    assert "customer_name || c.business_name" in deliv
