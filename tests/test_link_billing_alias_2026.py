"""Recurrence prevention: link_billing_alias binds marketing ↔ billing ids.

Covers first link, idempotent re-link, same-id no-op, conflict refusal, and
activate_plan wiring. Offline — tmp clients_store only.
"""

from __future__ import annotations

import json
import os

from app.marketing import clients_store

MKT = "jiya-makeover"
BILL = "d79d690f61b3"  # pragma: allowlist secret
OTHER = "other-tenant-9f3a"


def _seed(monkeypatch, tmp_path, rows):
    path = str(tmp_path / "marketing_clients.jsonl")
    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_link_first_activation(monkeypatch, tmp_path):
    _seed(
        monkeypatch,
        tmp_path,
        [{"id": MKT, "business_name": "Jiya", "plan": "starter", "status": "active"}],
    )
    res = clients_store.link_billing_alias(MKT, BILL, actor="test")
    assert res["ok"] is True
    assert res["linked"] is True
    assert res["reason"] == "linked"
    assert clients_store.canonical_client_id(BILL) == MKT
    assert BILL in (clients_store.get_client(MKT) or {}).get("billing_client_ids", [])


def test_link_idempotent_repeat(monkeypatch, tmp_path):
    _seed(
        monkeypatch,
        tmp_path,
        [
            {
                "id": MKT,
                "business_name": "Jiya",
                "billing_client_ids": [BILL],
                "plan": "starter",
            }
        ],
    )
    res = clients_store.link_billing_alias(MKT, BILL, actor="test")
    assert res["ok"] is True
    assert res["linked"] is False
    assert res["reason"] == "already_linked"


def test_link_same_id_noop(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path, [{"id": MKT, "business_name": "Jiya"}])
    res = clients_store.link_billing_alias(MKT, MKT, actor="test")
    assert res["ok"] is True
    assert res["linked"] is False
    assert res["reason"] == "same_id"


def test_link_conflict_other_tenant(monkeypatch, tmp_path):
    _seed(
        monkeypatch,
        tmp_path,
        [
            {"id": MKT, "business_name": "Jiya"},
            {
                "id": OTHER,
                "business_name": "Other",
                "billing_client_ids": [BILL],
            },
        ],
    )
    res = clients_store.link_billing_alias(MKT, BILL, actor="test")
    assert res["ok"] is False
    assert res["reason"] == "conflict"
    assert res.get("owner") == OTHER
    # Jiya must NOT have stolen the alias
    assert not (clients_store.get_client(MKT) or {}).get("billing_client_ids")


def test_link_conflict_direct_marketing_id(monkeypatch, tmp_path):
    _seed(
        monkeypatch,
        tmp_path,
        [
            {"id": MKT, "business_name": "Jiya"},
            {"id": OTHER, "business_name": "Other"},
        ],
    )
    res = clients_store.link_billing_alias(MKT, OTHER, actor="test")
    assert res["ok"] is False
    # Direct marketing id resolves via get_client first → "conflict" (or
    # conflict_direct if resolution order changes). Either refuses the steal.
    assert res["reason"] in ("conflict", "conflict_direct")
    assert res.get("owner") == OTHER


def test_link_marketing_missing(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path, [])
    res = clients_store.link_billing_alias(MKT, BILL, actor="test")
    assert res["ok"] is False
    assert res["reason"] == "marketing_not_found"


def test_link_reverse_lookup(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path, [{"id": MKT, "business_name": "Jiya"}])
    clients_store.link_billing_alias(MKT, BILL, actor="test")
    assert (clients_store.resolve_client(BILL) or {}).get("id") == MKT
    assert clients_store.canonical_client_id(BILL) == MKT
    assert clients_store.canonical_client_id(MKT) == MKT


def test_activate_plan_links_alias(monkeypatch, tmp_path):
    """activate_plan(billing_id) must update marketing plan + link alias."""
    _seed(
        monkeypatch,
        tmp_path,
        [
            {
                "id": MKT,
                "business_name": "Jiya",
                "billing_client_ids": [BILL],
                "plan": "trial",
                "status": "active",
            }
        ],
    )
    from app.billing import usage

    # Avoid DB subscription side effects in this unit test.
    class _NoDB:
        def __enter__(self):
            raise RuntimeError("no db in unit test")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("app.models.base.get_db_session", lambda: _NoDB())
    ok = usage.activate_plan(BILL, "starter", ensure_subscription=False)
    assert ok is True
    rec = clients_store.get_client(MKT) or {}
    assert rec.get("plan") == "starter"
    assert BILL in (rec.get("billing_client_ids") or [])
