"""Tests for the safe approval remediation (app/marketing/approval_remediation.py).

Hermetic: content_approval store, client list, cancel, and team feed are all
monkeypatched, so NO live production data is read or mutated. Proves the business
outcome (inactive-client stuck drafts get expired) AND the safety invariants
(active-client drafts are NEVER cancelled; execution is gated; dry-run changes nothing).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.marketing import approval_remediation as ar
from app.marketing import clients_store, content_approval
from app.platform import team


def _iso(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


_STATES = {
    "a1": {
        "client_id": "jiya-makeover",
        "status": "approved",
        "created_at": _iso(72),
        "content": {"title": "Jiya ad"},
    },
    "a2": {
        "client_id": "105a5a749a81",
        "status": "pending",
        "created_at": _iso(72),
        "content": {"title": "Naya video ad"},
    },
    "a3": {
        "client_id": "e02c6e4f1f07",
        "status": "pending",
        "created_at": _iso(72),
        "content": {"title": "Naya video ad"},
    },
    "a4": {
        "client_id": "105a5a749a81",
        "status": "published",
        "created_at": _iso(72),
    },  # terminal -> ignored
    "a5": {
        "client_id": "dfbcbc8e5a08",
        "status": "pending",
        "created_at": _iso(2),
    },  # too young -> ignored
}

# Fake billing alias fixture (not a credential) — same pattern as test_delivery_assurance.
_JIYA_BILLING_ALIAS = "d79d690f61b3"  # pragma: allowlist secret


def _wire(monkeypatch):
    monkeypatch.setattr(content_approval, "_latest_states", lambda: dict(_STATES))
    monkeypatch.setattr(
        clients_store,
        "list_clients",
        lambda status=None, product=None: [
            {"id": "jiya-makeover", "billing_client_ids": [_JIYA_BILLING_ALIAS]}
        ],
    )
    monkeypatch.setattr(clients_store, "canonical_client_id", lambda cid: str(cid or "").strip())
    calls = []
    monkeypatch.setattr(
        content_approval,
        "cancel",
        lambda aid, actor="customer", note="": calls.append(aid) or {"ok": True},
    )
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(ar, "_backup_store", lambda: "data/content_approvals.jsonl.bak-test")
    return calls


def test_plan_classifies_inactive_expire_vs_active_escalate(monkeypatch):
    _wire(monkeypatch)
    plan = ar.plan_remediation(min_age_hours=48)
    assert plan["status"] == "success"
    assert plan["total_stuck"] == 3  # a1,a2,a3 (a4 terminal, a5 young excluded)
    assert plan["expire_candidates"] == 2  # a2,a3 inactive
    assert plan["escalate_active"] == 1  # a1 jiya (active)
    esc_ids = {r["id"] for r in plan["escalate_sample"]}
    assert "a1" in esc_ids


def test_dry_run_changes_nothing(monkeypatch):
    calls = _wire(monkeypatch)
    res = ar.execute_remediation(min_age_hours=48, dry_run=True)
    assert res["expired"] == 0
    assert res["skipped"] == 2
    assert calls == []  # cancel never called


def test_flag_off_is_a_hard_gate(monkeypatch):
    calls = _wire(monkeypatch)
    monkeypatch.delenv("APPROVAL_REMEDIATION", raising=False)
    res = ar.execute_remediation(min_age_hours=48, dry_run=False)  # dry_run False but flag off
    assert res["expired"] == 0
    assert calls == []  # gate holds


def test_execute_expires_only_inactive_never_active(monkeypatch):
    calls = _wire(monkeypatch)
    monkeypatch.setenv("APPROVAL_REMEDIATION", "1")
    res = ar.execute_remediation(min_age_hours=48, dry_run=False)
    assert res["expired"] == 2  # a2, a3
    assert set(calls) == {"a2", "a3"}  # ONLY inactive-client drafts cancelled
    assert "a1" not in calls  # active client (Jiya) NEVER touched
    assert res["backup_path"]  # backup taken before mutation


def test_never_raises_on_store_error(monkeypatch):
    monkeypatch.setattr(
        content_approval,
        "_latest_states",
        lambda: (_ for _ in ()).throw(RuntimeError("store down")),
    )
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None, product=None: [])
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    plan = ar.plan_remediation()
    assert plan["total_stuck"] == 0  # degrades to empty, no raise


def test_client_inventory_jiya_alias_resolves(monkeypatch):
    """WS-2 inventory: billing alias -> canonical; active Jiya stuck counts as escalate path."""
    _wire(monkeypatch)
    monkeypatch.setattr(
        clients_store,
        "get_client",
        lambda cid: (
            {
                "id": "jiya-makeover",
                "business_name": "Jiya Makeover",
                "billing_client_ids": [_JIYA_BILLING_ALIAS],
            }
            if cid in ("jiya-makeover", _JIYA_BILLING_ALIAS)
            else None
        ),
    )
    monkeypatch.setattr(
        clients_store,
        "canonical_client_id",
        lambda cid: (
            "jiya-makeover" if cid in ("jiya-makeover", _JIYA_BILLING_ALIAS) else str(cid or "")
        ),
    )
    monkeypatch.setattr(
        ar,
        "_meta_channel_status",
        lambda canonical_id, aliases=None: {
            "connected": False,
            "has_page_id": False,
            "has_instagram": False,
            "scope": "none",
        },
    )
    inv = ar.client_inventory(_JIYA_BILLING_ALIAS, min_age_hours=48)
    assert inv["status"] == "success"
    assert inv["canonical_id"] == "jiya-makeover"
    assert inv["client_active"] is True
    assert inv["stuck_count"] == 1
    assert inv["stuck_sample"][0]["id"] == "a1"
    assert inv["meta_channel"]["connected"] is False
    assert "approve" in inv["recommended_recovery"] or "meta" in inv["recommended_recovery"]


def test_meta_channel_status_never_returns_tokens(monkeypatch):
    import app.integrations.meta_graph as mg

    monkeypatch.setattr(
        mg,
        "_read_conns",
        lambda: [
            {
                "client_id": "jiya-makeover",
                "page_id": "page1",
                "page_access_token": "SECRET_SHOULD_NOT_LEAK",
                "instagram_account_id": "ig1",
            }
        ],
    )
    st = ar._meta_channel_status("jiya-makeover", [_JIYA_BILLING_ALIAS])
    assert st["connected"] is True
    assert st["has_page_id"] is True
    assert st["has_instagram"] is True
    assert "SECRET_SHOULD_NOT_LEAK" not in str(st)
    assert "page_access_token" not in st


def test_admin_approval_remediation_routes_registered():
    from app.api.admin_dashboard import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/api/admin/approval-remediation/plan" in paths
    assert "/api/admin/approval-remediation/client/{client_id}" in paths


def test_admin_approval_remediation_plan_endpoint_shape(monkeypatch):
    import asyncio

    from app.api import admin_dashboard

    monkeypatch.setattr(
        ar,
        "plan_remediation",
        lambda min_age_hours=48.0: {
            "status": "success",
            "total_stuck": 3,
            "expire_candidates": 2,
            "escalate_active": 1,
        },
    )
    res = asyncio.run(
        admin_dashboard.admin_approval_remediation_plan(min_age_hours=48.0, _user=object())
    )
    assert res["ok"] is True
    assert res["escalate_active"] == 1


def test_approval_remediation_flag_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "APPROVAL_REMEDIATION" in AUTOMATION_FLAGS
