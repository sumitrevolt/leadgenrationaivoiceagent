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


def _wire(monkeypatch):
    monkeypatch.setattr(content_approval, "_latest_states", lambda: dict(_STATES))
    monkeypatch.setattr(
        clients_store,
        "list_clients",
        lambda status=None, product=None: [
            {"id": "jiya-makeover", "billing_client_ids": ["d79d690f61b3"]}
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
