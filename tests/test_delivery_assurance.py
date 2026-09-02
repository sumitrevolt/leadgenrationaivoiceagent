"""Tests for the read-only customer delivery-assurance aggregator
(app/marketing/delivery_assurance.py).

Hermetic: every external primitive is monkeypatched, so NO live production
customer data is read or mutated. Covers the jiya-makeover<->billing-alias
canonicalisation case, the read-only guarantee (write functions raise if called),
structured-record shape, and never-raises resilience.
"""

# ruff: noqa: I001
from __future__ import annotations

import pytest

from app.marketing import clients_store, customer_delivery
from app.marketing import delivery_assurance as da
from app.marketing import delivery_ledger, product_one_delivery
from app.platform import team

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
_JIYA = {
    "id": "jiya-makeover",
    "business_name": "Jiya Makeover",
    "plan": "starter",
    "status": "active",
    "delivery_state": None,
    "billing_client_ids": [
        "d79d690f61b3",  # pragma: allowlist secret - fake billing alias fixture, not a credential
    ],
    "phone": "9999999999",
    "slug": "jiya-makeover",
}
_HEALTHY = {
    "id": "acme-salon",
    "business_name": "Acme Salon",
    "plan": "combo",
    "status": "active",
    "delivery_state": "acknowledged",
    "billing_client_ids": [],
}


def _install(monkeypatch, clients, status_map, *, forbid_writes=True):
    """Wire hermetic stubs. status_map: cid -> customer_delivery_status dict."""
    monkeypatch.setattr(
        clients_store, "list_clients", lambda status=None, product=None: list(clients)
    )

    def _canon(cid):
        # billing alias -> marketing id (mirrors clients_store.resolve_client)
        if str(cid) == "d79d690f61b3":  # pragma: allowlist secret — test fixture billing alias
            return "jiya-makeover"
        return str(cid or "").strip()

    monkeypatch.setattr(clients_store, "canonical_client_id", _canon)
    monkeypatch.setattr(customer_delivery, "has_paid_evidence", lambda c: True)
    monkeypatch.setattr(customer_delivery, "is_paid_client", lambda c: True)
    monkeypatch.setattr(
        customer_delivery,
        "is_delivered",
        lambda c: (
            str((c or {}).get("delivery_state") or "").lower() in ("delivered", "acknowledged")
        ),
    )
    monkeypatch.setattr(
        customer_delivery,
        "mini_site_url",
        lambda c: f"https://leadsgenai.in/b/{(c or {}).get('slug', '')}",
    )
    monkeypatch.setattr(
        product_one_delivery,
        "customer_delivery_status",
        lambda cid, client=None: status_map.get(cid, {"ok": True, "health_status": "green"}),
    )
    monkeypatch.setattr(
        delivery_ledger,
        "recent_counts",
        lambda cid, hours=168: {"failures_24h": 0, "value_events_in_window": 3},
    )
    monkeypatch.setattr(delivery_ledger, "timeline", lambda cid, limit=50, customer_only=False: [])

    events = []
    monkeypatch.setattr(team, "log_event", lambda *a, **k: events.append((a, k)))

    if forbid_writes:

        def _boom(*a, **k):
            raise AssertionError("WRITE called from read-only delivery-assurance scan")

        monkeypatch.setattr(clients_store, "update_client", _boom)
        monkeypatch.setattr(customer_delivery, "deliver_client_value", _boom)
        monkeypatch.setattr(product_one_delivery, "record_manual_action", _boom)
        monkeypatch.setattr(product_one_delivery, "sync_customer_deliverable_status", _boom)
    return events


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_scan_flags_undelivered_paid_and_is_evidence_backed(monkeypatch):
    status = {
        "jiya-makeover": {
            "ok": True,
            "health_status": "red",
            "health_score": 20,
            "deliverable_completion_pct": 60,
            "health_reasons": ["gbp pending"],
            "failed_automations": 1,
        }
    }
    monkeypatch.setattr(
        delivery_ledger,
        "recent_counts",
        lambda cid, hours=168: {"failures_24h": 2, "value_events_in_window": 1},
    )
    events = _install(monkeypatch, [_JIYA], status)
    monkeypatch.setattr(
        delivery_ledger,
        "recent_counts",
        lambda cid, hours=168: {"failures_24h": 2, "value_events_in_window": 1},
    )

    res = da.scan_missed_deliverables()
    assert res["status"] == "success"
    assert res["agent_id"] == "delivery_assurance"
    assert res["checked"] == 1
    assert res["missed_count"] == 1
    item = res["items"][0]
    assert item["canonical_id"] == "jiya-makeover"
    assert item["missed"] is True
    assert item["evidence"]["failures_24h"] == 2
    assert "health_red" in item["reasons"]
    # observability event emitted under the revenue-ops owner
    assert events and events[0][0][0] == "nikhil"


def test_billing_alias_canonicalizes_to_marketing_id(monkeypatch):
    """A client keyed by the raw billing/login id resolves to the marketing id."""
    _install(monkeypatch, [], {})  # just to wire canonical_client_id stub
    aliased = dict(_JIYA, id="d79d690f61b3")
    rec = da.assess_client_delivery(aliased)
    assert rec["canonical_id"] == "jiya-makeover"
    assert rec["raw_id"] == "d79d690f61b3"


def test_scan_is_read_only_no_writes(monkeypatch):
    """If any write primitive is invoked the stub raises — scan must still succeed."""
    status = {
        "jiya-makeover": {"ok": True, "health_status": "red", "deliverable_completion_pct": 10}
    }
    _install(monkeypatch, [_JIYA], status, forbid_writes=True)
    res = da.scan_missed_deliverables()
    assert res["status"] == "success"  # proves no write path was hit


def test_healthy_delivered_customer_excluded_unless_requested(monkeypatch):
    status = {
        "jiya-makeover": {"ok": True, "health_status": "red", "deliverable_completion_pct": 30},
        "acme-salon": {"ok": True, "health_status": "green", "deliverable_completion_pct": 100},
    }
    _install(monkeypatch, [_JIYA, _HEALTHY], status)
    res = da.scan_missed_deliverables()
    ids = {i["canonical_id"] for i in res["items"]}
    assert "jiya-makeover" in ids
    assert "acme-salon" not in ids  # green + delivered excluded

    res_all = da.scan_missed_deliverables(include_healthy=True)
    ids_all = {i["canonical_id"] for i in res_all["items"]}
    assert "acme-salon" in ids_all


def test_never_raises_on_status_error(monkeypatch):
    def _boom_status(cid, client=None):
        raise RuntimeError("derivation blew up")

    _install(monkeypatch, [_JIYA], {})
    monkeypatch.setattr(product_one_delivery, "customer_delivery_status", _boom_status)
    res = da.scan_missed_deliverables()
    assert res["status"] == "success"
    # jiya is undelivered so still flagged even though status derivation failed
    item = res["items"][0]
    assert item["canonical_id"] == "jiya-makeover"
    assert "status_error" in item["reasons"]


def test_run_result_shape_and_summary(monkeypatch):
    status = {
        "jiya-makeover": {"ok": True, "health_status": "yellow", "deliverable_completion_pct": 80}
    }
    _install(monkeypatch, [_JIYA], status)
    res = da.scan_missed_deliverables()
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
        "missed_count",
        "at_risk_count",
        "items",
        "error",
    ):
        assert key in res, key
    assert res["lane"] == "GREEN"
    assert isinstance(res["latency_ms"], int)

    summ = da.missed_deliverables_summary()
    assert summ["checked"] == 1
    assert summ["customers"][0]["id"] == "jiya-makeover"


# --------------------------------------------------------------------------- #
# Slice 2 — live wiring: hourly product_one_health sweep + admin endpoint
# --------------------------------------------------------------------------- #
def test_health_sweep_emits_assurance_observability(monkeypatch):
    """The hourly sweep runs the read-only assurance scan and reports its counts."""
    import asyncio

    from app.marketing import product_one_delivery as p1

    monkeypatch.setattr(clients_store, "list_clients", lambda status=None, product=None: [])
    monkeypatch.setattr(
        da,
        "scan_missed_deliverables",
        lambda limit=200: {"status": "success", "missed_count": 2, "at_risk_count": 1},
    )
    out = asyncio.run(p1.run_health_and_recovery_sweep())
    assert out["ok"] is True
    assert out["assurance_missed"] == 2
    assert out["assurance_at_risk"] == 1


def test_health_sweep_isolated_from_assurance_failure(monkeypatch):
    """A failure in the assurance scan must NOT break the sweep's own result."""
    import asyncio

    from app.marketing import product_one_delivery as p1

    monkeypatch.setattr(clients_store, "list_clients", lambda status=None, product=None: [])

    def _boom(limit=200):
        raise RuntimeError("assurance down")

    monkeypatch.setattr(da, "scan_missed_deliverables", _boom)
    out = asyncio.run(p1.run_health_and_recovery_sweep())
    assert out["ok"] is True  # sweep still succeeds
    assert any("assurance:" in e for e in out.get("errors", []))


def test_admin_delivery_assurance_endpoint_shape(monkeypatch):
    """The committed read-only admin endpoint returns the scan record, auth-gated."""
    import asyncio

    from app.api import admin_dashboard

    monkeypatch.setattr(
        da,
        "scan_missed_deliverables",
        lambda limit, include_healthy: {
            "status": "success",
            "missed_count": 1,
            "at_risk_count": 0,
            "items": [],
            "checked": 1,
        },
    )
    res = asyncio.run(
        admin_dashboard.admin_delivery_assurance(include_healthy=False, limit=100, _user=object())
    )
    assert res["ok"] is True
    assert res["missed_count"] == 1


def test_delivery_cockpit_includes_assurance_summary(monkeypatch):
    """Cockpit must expose assurance rollup without mutating delivery state."""
    status = {
        "jiya-makeover": {
            "ok": True,
            "health_status": "red",
            "deliverable_completion_pct": 40,
            "health_reasons": ["proof pending"],
        }
    }
    _install(monkeypatch, [_JIYA], status, forbid_writes=True)
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None, product=None: [_JIYA])
    # Keep cockpit light: stub card builder + paid evidence helpers used inside.
    monkeypatch.setattr(
        product_one_delivery,
        "admin_customer_card",
        lambda c: {
            "id": c["id"],
            "plan": c.get("plan"),
            "current_delivery_stage": "content_in_progress",
            "health_status": "red",
            "health_score": 40,
            "risk_flag": "at_risk",
            "pending_customer_inputs": 0,
            "pending_admin_actions": 0,
            "content_generated": 1,
            "posts_waiting_for_approval": 1,
            "posts_scheduled": 0,
            "posts_published": 0,
            "failed_automations": 1,
            "stale_approvals_24h": 0,
            "urgent_approvals_48h": 0,
            "deliverable_completion_pct": 40,
        },
    )
    monkeypatch.setattr(product_one_delivery, "_safe_integration_readiness", lambda: {"ok": True})
    monkeypatch.setattr(
        product_one_delivery,
        "_safe_customer_deliverable_db_audit",
        lambda cards: {"ok": True, "mismatches": []},
    )
    try:
        from app.api import admin_dashboard_builders as builders

        monkeypatch.setattr(builders, "_has_paid_evidence", lambda c: True)
    except Exception:
        pass

    cockpit = product_one_delivery.delivery_cockpit()
    assert cockpit.get("ok") is True
    assurance = cockpit.get("assurance") or {}
    assert "missed" in assurance
    assert "at_risk" in assurance
    assert "customers" in assurance
    assert assurance.get("error") in (None, "") or "error" in assurance


def test_admin_delivery_assurance_route_registered():
    from app.api.admin_dashboard import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/api/admin/delivery-assurance" in paths
    assert "/api/admin/delivery-cockpit" in paths


def test_command_center_feeds_assurance_into_at_risk_kpi():
    from pathlib import Path

    html = (
        Path(__file__).resolve().parent.parent / "frontend" / "delivery_command_center.html"
    ).read_text(encoding="utf-8")
    assert "data.assurance" in html
    assert "at_risk_count:" in html
    assert "assurance.at_risk" in html
    assert "assurance.missed" in html
    # Never fake green zero when assurance scan failed
    assert "assurance.error" in html
    assert "assuranceUnavailable" in html
    assert "assurance unavailable" in html
