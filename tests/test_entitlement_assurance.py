"""Tests for the read-only billing/entitlement-assurance aggregator
(app/billing/entitlement_assurance.py).

Hermetic: every external primitive is monkeypatched (clients_store.list_clients +
canonical_client_id, gst_invoice._read, subscription.PRICING_PLANS,
packages.get_public_packages/get_packages, team.log_event), so NO live production
tenant/invoice data is read and — critically — NO billing state is ever mutated.

Covers: paid-no-invoice detection, canonical billing-alias resolution
(a client keyed by billing id d79d690f61b3 resolves to jiya-makeover), the
read-only guarantee (any billing write raises if invoked -> scan still succeeds),
invoice-vs-subscription mismatch, unknown-plan + entitlement-drift, never-raises
resilience, and the AgentRunResult-shaped structure.
"""

# ruff: noqa: I001
from __future__ import annotations

from app.marketing import clients_store, packages
from app.billing import gst_invoice, subscription
from app.billing import entitlement_assurance as ea
from app.platform import team

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
_ALIAS = "d79d690f61b3"  # pragma: allowlist secret - fake billing alias fixture, not a credential

_JIYA = {
    "id": "jiya-makeover",
    "business_name": "Jiya Makeover",
    "plan": "starter",
    "status": "active",
    "delivery_state": None,
    "billing_client_ids": [_ALIAS],
    "phone": "9999999999",
    "slug": "jiya-makeover",
}


def _invoice(client_id, number="INV/2026-27/0001", plan="starter", gross=1999):
    return {
        "client_id": client_id,
        "number": number,
        "fy": "2026-27",
        "date": "2026-07-01",
        "plan": plan,
        "gross_inr": gross,
    }


def _install(
    monkeypatch,
    clients,
    invoices,
    *,
    forbid_writes=True,
    public_packages=None,
    all_packages=None,
    pricing_plans=None,
):
    """Wire hermetic billing/tenant stubs. Returns the captured team events list."""
    monkeypatch.setattr(
        clients_store,
        "list_clients",
        lambda status=None, product=None: [
            c
            for c in clients
            if status is None or str(c.get("status") or "").lower() == str(status).lower()
        ],
    )

    def _canon(cid):
        # billing alias -> marketing id (mirrors clients_store.resolve_client)
        if str(cid) == _ALIAS:
            return "jiya-makeover"
        return str(cid or "").strip()

    monkeypatch.setattr(clients_store, "canonical_client_id", _canon)

    # immutable Rule-46 ledger reader — the ONLY invoice read the module touches
    monkeypatch.setattr(gst_invoice, "_read", lambda: [dict(r) for r in invoices])

    if public_packages is None:
        public_packages = [
            {"key": "starter", "price_inr_month": 1999, "features": ["a", "b"]},
            {"key": "advanced", "price_inr_month": 5999, "features": ["x"]},
        ]
    monkeypatch.setattr(
        packages,
        "get_public_packages",
        lambda include_trial=False: [dict(p) for p in public_packages],
    )
    if all_packages is None:
        all_packages = [
            *public_packages,
            {"key": "growth", "price_inr_month": 2999, "features": ["g"]},
        ]
    monkeypatch.setattr(
        packages, "get_packages", lambda include_trial=False: [dict(p) for p in all_packages]
    )

    # subscription plan catalog reader (voice/combo/data ids in prod) — controlled here
    monkeypatch.setattr(subscription, "PRICING_PLANS", pricing_plans or {})

    events: list = []
    monkeypatch.setattr(team, "log_event", lambda *a, **k: events.append((a, k)))

    if forbid_writes:

        def _boom(*a, **k):
            raise AssertionError("BILLING WRITE called from read-only entitlement scan")

        # every mutation surface the module could conceivably touch
        monkeypatch.setattr(gst_invoice, "create_invoice", _boom)
        monkeypatch.setattr(gst_invoice, "void_invoice", _boom)
        monkeypatch.setattr(gst_invoice, "on_payment_success", _boom)
        monkeypatch.setattr(gst_invoice, "_append", _boom)
        monkeypatch.setattr(clients_store, "update_client", _boom)
        monkeypatch.setattr(clients_store, "set_status", _boom)
    return events


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_paid_active_client_without_invoice_flagged(monkeypatch):
    """Active paid plan + ZERO invoice evidence -> paid_no_invoice (revenue leak)."""
    events = _install(monkeypatch, [_JIYA], [])  # no invoices at all
    res = ea.scan_entitlements()

    assert res["status"] == "success"
    assert res["agent_id"] == "entitlement_assurance"
    assert res["domain"] == "billing"
    assert res["checked"] == 1
    assert res["counts"]["paid_no_invoice"] == 1
    assert res["counts"]["flagged"] == 1
    types = {i["type"] for i in res["issues"]}
    assert "paid_no_invoice" in types
    sample = next(i for i in res["issues"] if i["type"] == "paid_no_invoice")["sample"][0]
    assert sample["id"] == "jiya-makeover"
    # observability event emitted under the revenue-ops owner, warn (something flagged)
    assert events and events[0][0][0] == "nikhil"
    assert events[0][1].get("status") == "warn"


def test_billing_alias_resolves_to_marketing_id(monkeypatch):
    """Invoice under the raw billing/login id credits the marketing tenant."""
    inv = _invoice(_ALIAS)  # invoice keyed by the billing alias, not the marketing id
    _install(monkeypatch, [_JIYA], [inv])
    res = ea.scan_entitlements()

    assert res["counts"]["paid_no_invoice"] == 0  # alias resolved -> tenant IS invoiced

    # assess a client keyed by the raw alias -> canonical marketing id + invoice match
    aliased = dict(_JIYA, id=_ALIAS, billing_client_ids=[])
    idx = ea._invoice_index([inv])
    rec = ea.assess_client_entitlement(aliased, idx, ea._plan_catalog())
    assert rec["canonical_id"] == "jiya-makeover"
    assert rec["raw_id"] == _ALIAS
    assert rec["has_invoice"] is True
    assert rec["paid_no_invoice"] is False


def test_invoice_without_active_subscription_flagged(monkeypatch):
    """Has an invoice but subscription is non-active (not churned) -> mismatch."""
    paused = {
        "id": "acme-salon",
        "business_name": "Acme Salon",
        "plan": "advanced",
        "status": "paused",
        "billing_client_ids": [],
    }
    _install(monkeypatch, [paused], [_invoice("acme-salon", plan="advanced", gross=5999)])
    res = ea.scan_entitlements()

    assert res["counts"]["invoice_without_active_subscription"] == 1
    assert res["counts"]["paid_no_invoice"] == 0  # paused != active-paid, so not this bucket
    types = {i["type"] for i in res["issues"]}
    assert "invoice_without_active_subscription" in types


def test_cancelled_tenant_with_invoice_not_flagged(monkeypatch):
    """A churned/cancelled tenant with historical invoices is EXPECTED, not a bug."""
    cancelled = {
        "id": "gone-biz",
        "business_name": "Gone Biz",
        "plan": "starter",
        "status": "cancelled",
        "billing_client_ids": [],
    }
    _install(monkeypatch, [cancelled], [_invoice("gone-biz")])
    res = ea.scan_entitlements()
    assert res["counts"]["invoice_without_active_subscription"] == 0
    assert res["counts"]["flagged"] == 0


def test_unknown_plan_flagged(monkeypatch):
    """Active paid tenant on a plan absent from the catalog -> unknown_plan."""
    mystery = {
        "id": "mystery-biz",
        "business_name": "Mystery Biz",
        "plan": "mystery_plan",
        "status": "active",
        "billing_client_ids": [],
    }
    # give it an invoice so paid_no_invoice does not also fire (isolate unknown_plan)
    _install(monkeypatch, [mystery], [_invoice("mystery-biz", plan="mystery_plan")])
    res = ea.scan_entitlements()
    assert res["counts"]["unknown_plan"] == 1
    assert res["counts"]["paid_no_invoice"] == 0


def test_entitlement_drift_flagged(monkeypatch):
    """Active paid plan with features but not-yet-delivered -> entitlement_drift."""
    undelivered = {
        "id": "fresh-biz",
        "business_name": "Fresh Biz",
        "plan": "starter",
        "status": "active",
        "delivery_state": None,  # entitled features not reflected in delivered state
        "billing_client_ids": [],
    }
    _install(monkeypatch, [undelivered], [_invoice("fresh-biz")])
    res = ea.scan_entitlements()
    assert res["counts"]["entitlement_drift"] == 1
    assert res["counts"]["paid_no_invoice"] == 0  # invoiced, so not a leak

    # a delivered tenant on the same plan should NOT drift
    delivered = dict(undelivered, id="done-biz", delivery_state="acknowledged")
    _install(monkeypatch, [delivered], [_invoice("done-biz")])
    res2 = ea.scan_entitlements()
    assert res2["counts"]["entitlement_drift"] == 0


def test_scan_is_read_only_no_billing_mutation(monkeypatch):
    """If ANY billing write primitive is invoked the stub raises — scan must still
    succeed (proves the scan never mutates billing state)."""
    _install(monkeypatch, [_JIYA], [], forbid_writes=True)
    res = ea.scan_entitlements()
    assert res["status"] == "success"  # no write path was hit
    # and the summary wrapper is equally read-only
    summ = ea.entitlement_summary()
    assert summ["checked"] == 1


def test_never_raises_returns_shaped_error(monkeypatch):
    """A blow-up inside the per-tenant assessment degrades to a shaped error, not
    an exception."""
    events = _install(monkeypatch, [_JIYA], [])

    def _boom(*a, **k):
        raise RuntimeError("assessment exploded")

    monkeypatch.setattr(ea, "assess_client_entitlement", _boom)
    res = ea.scan_entitlements()
    assert res["status"] == "error"
    assert res["error"]
    # shape still intact + observability event went out as error
    for key in ("run_id", "agent_id", "domain", "lane", "issues", "counts", "latency_ms"):
        assert key in res
    assert events and events[0][1].get("status") == "error"


def test_never_raises_when_sources_fail(monkeypatch):
    """Even if the tenant list read itself raises, the scan returns a dict."""
    _install(monkeypatch, [_JIYA], [])

    def _boom(*a, **k):
        raise RuntimeError("clients store down")

    monkeypatch.setattr(clients_store, "list_clients", _boom)
    res = ea.scan_entitlements()  # must not raise
    assert isinstance(res, dict)
    assert res["checked"] == 0


def test_run_result_shape_and_summary(monkeypatch):
    _install(monkeypatch, [_JIYA], [])
    res = ea.scan_entitlements()
    for key in (
        "run_id",
        "agent_id",
        "domain",
        "lane",
        "status",
        "started_at",
        "completed_at",
        "latency_ms",
        "checked",
        "issues",
        "counts",
        "error",
    ):
        assert key in res, key
    assert res["agent_id"] == "entitlement_assurance"
    assert res["domain"] == "billing"
    assert res["lane"] == "GREEN"
    assert isinstance(res["latency_ms"], int)
    assert isinstance(res["issues"], list)
    for issue in res["issues"]:
        assert {"type", "count", "sample"} <= set(issue)

    summ = ea.entitlement_summary()
    assert summ["checked"] == 1
    assert "counts" in summ
    assert isinstance(summ["issues"], list)
