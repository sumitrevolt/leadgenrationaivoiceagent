"""Admin Command Center (Customer Delivery OS Phase 2) — business-outcome
front door. Covers: (1) _build_command_center's bucket definitions using real
fixture data (not just presence-checking — this is pure Python aggregation,
so real logic can be verified); (2) the _plan_price("trial") regression found
while building this (was silently attributing full Starter MRR to free-trial
signups); (3) the GET /api/admin/command-center endpoint; (4) static-HTML
presence for the new page + its main.py route."""

from fastapi.testclient import TestClient


def _override_admin(app):
    from app.api.auth_deps import require_admin

    app.dependency_overrides[require_admin] = lambda: {"username": "test"}


def _client(id, plan="starter", setup_done=True, status="active"):
    return {
        "id": id,
        "business_name": f"Biz {id}",
        "plan": plan,
        "product": "marketing",
        "status": status,
        "setup_done": setup_done,
    }


def _patch_sources(monkeypatch, clients, summaries, approvals):
    """summaries: dict[client_id -> summary dict]. approvals: list of
    {"client_id": ...} pending-approval rows (as content_approval.pending()
    itself returns — NOT pre-bucketed, to prove the builder buckets it)."""
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: clients,
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.summary",
        lambda cid: summaries.get(cid, {}),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.content_approval.pending",
        lambda client_id="": approvals,
        raising=False,
    )


def test_bucket_definitions_cover_each_customer_type(monkeypatch):
    """One customer of each type; each must land in exactly the buckets it
    qualifies for — this is the part that silently goes wrong (advisor-flagged)."""
    from app.api.admin_dashboard_builders import _build_command_center

    clients = [
        _client("trial1", plan="trial", setup_done=True),
        _client("stuck1", plan="starter", setup_done=False),
        _client("value1", plan="starter", setup_done=True),
        _client("fail1", plan="advanced", setup_done=True),
    ]
    summaries = {
        "trial1": {"value_delivered": False, "automation_failures": 0},
        "stuck1": {"value_delivered": False, "automation_failures": 0},
        "value1": {"value_delivered": True, "automation_failures": 0},
        "fail1": {"value_delivered": True, "automation_failures": 2},
    }
    approvals = [{"client_id": "value1"}, {"client_id": "value1"}, {"client_id": "fail1"}]
    _patch_sources(monkeypatch, clients, summaries, approvals)
    monkeypatch.setattr(
        "app.api.admin_dashboard_builders._has_paid_evidence",
        lambda c: str(c.get("plan")) != "trial",
    )

    out = _build_command_center()
    s = out["summary"]

    assert s["total_customers"] == 4
    assert s["paying_customers"] == 3  # all except trial1
    assert s["stuck_in_setup"] == 1  # only stuck1
    assert s["receiving_value"] == 2  # value1 + fail1
    assert s["failed_automation_count"] == 1  # only fail1
    assert s["pending_approvals_total"] == 3  # 2 + 1, summed once

    by_id = {c["id"]: c for c in out["per_customer"]}
    assert by_id["value1"]["pending_approvals"] == 2
    assert by_id["fail1"]["pending_approvals"] == 1
    assert by_id["stuck1"]["pending_approvals"] == 0
    assert by_id["trial1"]["mrr"] == 0  # trial must never bill as a paid tier


def test_revenue_excludes_trial_and_sums_by_plan(monkeypatch):
    from app.api.admin_dashboard_builders import _build_command_center

    clients = [
        _client("a", plan="starter"),
        _client("b", plan="starter"),
        _client("c", plan="trial"),
    ]
    _patch_sources(monkeypatch, clients, {}, [])
    monkeypatch.setattr(
        "app.api.admin_dashboard_builders._has_paid_evidence",
        lambda c: str(c.get("id")) in {"a", "b"},
    )

    out = _build_command_center()
    assert out["revenue"]["mrr_total"] == 1999 * 2
    assert out["revenue"]["by_plan"]["starter"] == {"count": 2, "mrr": 3998}
    assert out["revenue"]["by_plan"]["trial"] == {"count": 1, "mrr": 0}


def test_posts_failed_alone_also_counts_as_automation_issue(monkeypatch):
    """A customer with zero automation_failed events but a failed post-publish
    (post_failed, wired in the Marketing Calendar loop) must still surface in
    the Automation Issues bucket — not just the older automation_failed signal."""
    from app.api.admin_dashboard_builders import _build_command_center

    clients = [_client("only-post-failed")]
    summaries = {
        "only-post-failed": {"value_delivered": True, "automation_failures": 0, "posts_failed": 1}
    }
    _patch_sources(monkeypatch, clients, summaries, [])

    out = _build_command_center()
    assert out["summary"]["failed_automation_count"] == 1
    by_id = {c["id"]: c for c in out["per_customer"]}
    assert by_id["only-post-failed"]["automation_failures"] == 1


def test_selected_non_trial_without_payment_is_not_paying_or_mrr(monkeypatch):
    """A plan choice alone must not create revenue in the admin rollup."""
    from app.api.admin_dashboard_builders import _build_command_center

    clients = [_client("unpaid", plan="growth"), _client("paid", plan="starter")]
    _patch_sources(monkeypatch, clients, {}, [])
    monkeypatch.setattr(
        "app.api.admin_dashboard_builders._has_paid_evidence",
        lambda c: str(c.get("id")) == "paid",
    )

    out = _build_command_center()

    assert out["summary"]["paying_customers"] == 1
    assert out["revenue"]["mrr_total"] == 1999
    by_id = {c["id"]: c for c in out["per_customer"]}
    assert by_id["unpaid"]["mrr"] == 0
    assert by_id["paid"]["mrr"] == 1999


def test_pending_approvals_fetched_once_not_per_client(monkeypatch):
    """Backlog 2026-07-07 warned against a 4th duplicate aggregator; the
    contract here is content_approval.pending() is called with NO client_id
    filter exactly once, then bucketed in memory."""
    from app.api.admin_dashboard_builders import _build_command_center

    clients = [_client("a"), _client("b"), _client("c")]
    calls = []

    def _pending(client_id=""):
        calls.append(client_id)
        return [{"client_id": "a"}]

    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: clients,
        raising=False,
    )
    monkeypatch.setattr("app.marketing.delivery_ledger.summary", lambda cid: {}, raising=False)
    monkeypatch.setattr("app.marketing.content_approval.pending", _pending, raising=False)

    _build_command_center()
    assert calls == [""]  # exactly one call, no client_id filter


def test_empty_clients_never_raises(monkeypatch):
    from app.api.admin_dashboard_builders import _build_command_center

    _patch_sources(monkeypatch, [], {}, [])
    out = _build_command_center()
    assert out["summary"]["total_customers"] == 0
    assert out["revenue"]["mrr_total"] == 0
    assert out["per_customer"] == []


def test_plan_price_trial_is_free_not_starter_fallback():
    """Regression: get_packages() (no include_trial) doesn't contain the
    "trial" key, so _plan_price("trial") used to fall through to the
    min-nonzero-price fallback (₹1,999) instead of the real ₹0 trial price."""
    from app.api.admin_dashboard_builders import _client_mrr, _plan_price

    assert _plan_price("trial") == 0
    trial_client = {"id": "t1", "status": "active", "plan": "trial"}
    assert _client_mrr(trial_client) == 0


def test_plan_price_unknown_plan_still_falls_back_to_cheapest():
    """The min-nonzero fallback must still work for genuinely unrecognized
    plan keys (corrupt/legacy data) — only "trial" gets a real lookup now."""
    from app.api.admin_dashboard_builders import _plan_price

    assert _plan_price("some_garbage_plan_key") == 1999


def test_command_center_endpoint_returns_real_shape(monkeypatch):
    from app.main import app

    _override_admin(app)
    clients = [_client("x", plan="starter")]
    _patch_sources(
        monkeypatch, clients, {"x": {"value_delivered": True, "automation_failures": 0}}, []
    )
    monkeypatch.setattr(
        "app.api.admin_dashboard_builders._has_paid_evidence",
        lambda c: True,
    )

    with TestClient(app) as c:
        resp = c.get("/api/admin/command-center")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["summary"]["total_customers"] == 1
    assert body["summary"]["receiving_value"] == 1
    assert body["revenue"]["mrr_total"] == 1999
    app.dependency_overrides.clear()


def test_command_center_endpoint_requires_admin():
    from app.main import app

    app.dependency_overrides.clear()
    with TestClient(app) as c:
        resp = c.get("/api/admin/command-center")
    assert resp.status_code in (401, 403)


def _main_py():
    with open("app/main.py", encoding="utf-8") as f:
        return f.read()


def _page_html():
    with open("frontend/delivery_command_center.html", encoding="utf-8") as f:
        return f.read()


def test_page_route_registered_and_distinct_from_ops_command_center():
    src = _main_py()
    assert '@app.get("/app/delivery-command-center"' in src
    assert '@app.get("/app/command-center"' in src  # old ops page still intact, not replaced


def test_page_calls_real_endpoint_and_reuses_localstorage_auth_pattern():
    html = _page_html()
    assert '"/api/admin/delivery-cockpit"' in html
    assert '"/api/admin/delivery-logs"' in html
    assert 'localStorage.getItem("accessToken")' in html
    assert "hdrs()" in html


def test_delivery_cockpit_paying_kpi_matches_invoice_backed_revenue():
    """The live cockpit must not count a selected non-trial plan as paid.

    Revenue is invoice-backed; using a plan-count KPI beside it produced the
    contradictory live state "Paying 3 / MRR ₹0".
    """
    html = _page_html()
    assert "var payingCustomers = Number(revenue.paying_customers);" in html
    assert "paying_customers: payingCustomers" in html
    assert (
        'paying_customers: customers.filter(function(c){ return c.plan !== "trial"; }).length'
        not in html
    )
    assert "invoice-backed paying customers, monthly" in html


def test_page_has_all_six_kpi_labels():
    html = _page_html()
    for label in (
        "Total Customers",
        "Paying",
        "Stuck in Setup",
        "Receiving Value",
        "Automation Issues",
        "Pending Approvals",
    ):
        assert label in html


def test_page_has_useful_empty_state():
    html = _page_html()
    assert "Abhi koi active customer nahi" in html


def test_admin_dashboard_links_to_command_center():
    """A page with no inbound link is unreachable in practice — CLAUDE.md §4
    ("naya admin feature = UI tab SAATH hi") and §8 both require this."""
    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        html = f.read()
    assert 'href="/app/delivery-command-center"' in html


def test_admin_dashboard_never_calls_undefined_toast():
    """Regression guard: toast() was called in c360DeliverNow/c360ScrapeWebsite/
    c360ResetPassword/dqDeliverNow but only adminToast(msg,type) is defined —
    every click threw an uncaught ReferenceError with zero admin feedback on
    real customer-facing actions (Deliver Value Now, Reset Password, etc.)."""
    import re

    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        html = f.read()
    assert "function adminToast(" in html
    # The dashboard now has a compatibility wrapper that intentionally defines
    # toast(title, message) and delegates to adminToast(). Exclude that
    # declaration; only calls elsewhere must be covered by the wrapper.
    assert re.search(r"function toast\(title, message\)\s*\{", html)
    assert "adminToast(combined, type)" in html
