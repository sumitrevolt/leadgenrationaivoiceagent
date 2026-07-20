"""frontend/clients.html — admin Customer 360-lite (delivery timeline + Deliver
Now button). Static-HTML guard, mirrors tests/test_customer_dashboard_timeline_section.py's
style: confirms the new panel/functions exist and reference real endpoints,
without needing a live authenticated browser session."""


def _html():
    with open("frontend/clients.html", encoding="utf-8") as f:
        return f.read()


def test_delivery_panel_placeholder_exists():
    html = _html()
    assert 'id="deliveryPanel"' in html


def test_select_client_wires_delivery_panel_load():
    html = _html()
    idx = html.index("function selectClient(")
    snippet = html[idx : idx + 200]
    assert "loadDeliveryPanel()" in snippet


def test_delivery_panel_calls_real_admin_timeline_endpoint():
    html = _html()
    idx = html.index("function loadDeliveryPanel")
    snippet = html[idx : idx + 600]
    assert '"/api/admin/clients/" + encodeURIComponent(c.id) + "/timeline"' in snippet
    assert "hdrs()" in snippet  # reuses the existing auth-header helper, not a new one


def test_deliver_now_calls_real_admin_endpoint_and_reuses_helpers():
    html = _html()
    idx = html.index("async function deliverNow(")
    # Confirmation/audit commentary may grow; inspect the whole bounded handler.
    snippet = html[idx : html.index("\n  var TYPE_BADGE", idx)]
    assert "/deliver-now" in snippet
    assert 'method: "POST"' in snippet
    assert "hdrs()" in snippet
    assert "callApi(" in snippet  # reuses existing fetch wrapper, not a raw fetch()


def test_delivery_panel_handles_disabled_flag_gracefully():
    """CLIENT_TIMELINE=0 (default) must show a helpful message, not break."""
    html = _html()
    idx = html.index("function renderDeliveryPanel")
    snippet = html[idx : idx + 900]
    assert "enabled" in snippet
    assert "CLIENT_TIMELINE" in snippet


def test_no_undefined_css_classes_introduced():
    """The two real bugs caught during manual review: .btn.go and .citem don't
    exist in this file's CSS — confirm they were not left in the shipped code."""
    html = _html()
    idx = html.index("function renderDeliveryPanel")
    snippet = html[idx : idx + 1600]
    assert 'class="btn go"' not in snippet
    assert 'class="citem"' not in snippet
