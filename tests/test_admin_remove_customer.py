"""Admin full customer-removal endpoint (client.remove) — Estique-style cleanup.

Covers: confirm-required gate, portal-login revoke, content-schedule cancel,
autopilot prospect -> terminal removed (never re-contacted), brand-kit + derived
store file deletion, clients_store record deletion, idempotency replay, audit.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.marketing import (
    brand_kit,
    client_blog,
    clients_store,
    content_schedule,
    crm_lite,
    delivery_ledger,
    product_one_delivery,
)
from app.platform.sales_autopilot import policy as policy_mod
from app.platform.sales_autopilot import store as store
from app.platform.sales_autopilot.eligibility import INELIGIBLE, evaluate

CID = "81bd0bbe501d"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(policy_mod, "_POLICY_DIR", str(tmp_path))
    monkeypatch.setattr(policy_mod, "_POLICY_FILE", str(tmp_path / "policy.json"))

    from app.api import customer_auth

    monkeypatch.setattr(customer_auth, "_STORE", str(tmp_path / "customer_auth.jsonl"))

    monkeypatch.setattr(content_schedule, "_FILE", str(tmp_path / "content_schedule.jsonl"))
    monkeypatch.setattr(brand_kit, "_BRAND_DIR", str(tmp_path / "brand_kits"))
    monkeypatch.setattr(client_blog, "_DIR", tmp_path / "client_blogs")
    monkeypatch.setattr(crm_lite, "_CRM_DIR", str(tmp_path / "crm"))
    monkeypatch.setattr(product_one_delivery, "_DELIVERY_DIR", str(tmp_path / "pod"))
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "ledger"))
    monkeypatch.setattr(delivery_ledger, "_CONTENT_QUEUE_DIR", lambda: str(tmp_path / "cq"))

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "clients.jsonl"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    monkeypatch.delenv("SALES_AUTOPILOT_ENABLED", raising=False)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _seed(client, *, login=True, schedule=3, prospect=True, brand=True, derived=True, clients=True):
    from app.api import customer_auth

    if login:
        customer_auth.register_login(
            email="info@estiquesalonsnspa.com",
            password="PLACEHOLDER_PW_1234x",  # pragma: allowlist secret
            client_id=CID,
        )
    if schedule:
        for i in range(schedule):
            content_schedule.schedule(
                business_name="Estique Salon & Spa",
                niche="beauty_salon",
                date_iso=f"2026-08-{10+i:02d}",
                occasion=f"occasion{i}",
                channel="instagram",
                client_id=CID,
            )
    if prospect:
        store.upsert_prospect(
            {
                "id": "p_estique",
                "phone": "+919812345678",
                "business_name": "Estique Salon & Spa",
                "niche": "beauty_salon",
                "status": store.STATUS_CONVERTED,
                "converted_client_id": CID,
                "manual_owner_confirmed": True,
            }
        )
    if brand:
        brand_kit.save_brand(CID, {"business_name": "Estique Salon & Spa"})
    if derived:
        os.makedirs(os.path.join(str(tmp_root()), "pod"), exist_ok=True)
        with open(product_one_delivery._events_path(CID), "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "x"}) + "\n")
        os.makedirs(os.path.join(str(tmp_root()), "cq"), exist_ok=True)
        with open(
            os.path.join(str(tmp_root()), "cq", delivery_ledger._safe_stem(CID) + ".jsonl"),
            "a",
            encoding="utf-8",
        ) as f:
            f.write(json.dumps({"x": 1}) + "\n")
        os.makedirs(os.path.join(str(tmp_root()), "client_blogs"), exist_ok=True)
        with open(client_blog._path(CID), "a", encoding="utf-8") as f:
            f.write(json.dumps({"title": "post"}) + "\n")
        os.makedirs(os.path.join(str(tmp_root()), "crm"), exist_ok=True)
        with open(crm_lite._path(CID), "a", encoding="utf-8") as f:
            f.write(json.dumps({"c": 1}) + "\n")
    if clients:
        os.makedirs(os.path.dirname(clients_store._CLIENTS_FILE()) or ".", exist_ok=True)
        with open(clients_store._CLIENTS_FILE(), "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "business_name": "Estique Salon & Spa",
                        "id": CID,
                        "niche": "beauty_salon",
                        "phone": "+919812345678",
                        "status": "active",
                        "product": "marketing",
                    }
                )
                + "\n"
            )


def tmp_root():
    return os.path.dirname(os.path.abspath(store._PROSPECTS_FILE))


def test_remove_requires_confirm(client):
    _seed(client)
    r = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": False},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error"] == "confirm required"


def test_remove_customer_full_cleanup(client):
    _seed(client)
    r = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": True, "reason": "not a real customer"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["auth_logins_revoked"] == 1
    assert d["content_cancelled"] == 3
    assert d["prospects_removed"] == 1
    assert d["brand_kit_deleted"] is True
    assert d["delivery_deleted"] is True
    assert d["blogs_deleted"] is True
    assert d["crm_deleted"] is True
    assert d["content_queue_deleted"] is True
    assert d["clients_record_deleted"] is True

    # portal login gone
    from app.api import customer_auth

    assert customer_auth.client_has_login(CID) is False

    # scheduled content all cancelled, none pending
    remaining = content_schedule.list_scheduled()
    assert all(i.get("status") == "cancelled" for i in remaining)
    assert all(i.get("client_id") == CID for i in remaining)

    # autopilot prospect terminal removed + eligibility fail-closed
    rec = store.get_prospect("p_estique")
    assert rec["status"] == store.STATUS_REMOVED
    assert (rec.get("converted_client_id") or "") == ""
    assert rec.get("removed_reason") == "not a real customer"
    # Inject a fully-PERMISSIVE policy on purpose: with the engine disabled the very
    # first gate short-circuits to "engine_disabled", which would make this assertion
    # pass for the wrong reason. Forcing every earlier gate open proves the removal
    # itself is what blocks re-contact.
    permissive = policy_mod.Policy(
        {
            "enabled": True,
            "channels": ["whatsapp"],
            "whatsapp_enabled": True,
            "kill_switches": {},
        }
    )
    elig = evaluate(
        {
            "id": "p_estique",
            "phone": "+919812345678",
            "niche": "beauty_salon",
            "consent_basis": "owner_confirmed",
        },
        channel="whatsapp",
        step="initial",
        pol=permissive,
    )
    assert elig["decision"] == INELIGIBLE
    assert "customer_removed" in elig["reason_codes"]

    # derived files gone
    assert not os.path.exists(product_one_delivery._events_path(CID))
    assert not os.path.exists(str(client_blog._path(CID)))
    assert not os.path.exists(crm_lite._path(CID))
    assert not os.path.exists(
        os.path.join(tmp_root(), "cq", delivery_ledger._safe_stem(CID) + ".jsonl")
    )

    # clients_store record gone
    assert clients_store.get_client(CID) is None


def test_remove_customer_idempotent_replay(client, monkeypatch):
    from app.platform import admin_idempotency as idem

    class _FakeRedis:
        def __init__(self):
            self.store = {}

        def set(self, k, v, nx=False, ex=None):
            if nx and k in self.store:
                return None
            self.store[k] = v
            return True

        def get(self, k):
            return self.store.get(k)

    # ONE shared instance — `lambda: _FakeRedis()` would mint a fresh empty store on
    # every call, so the stored result could never be found and replay never proves out.
    _fake = _FakeRedis()
    monkeypatch.setattr(idem, "_redis", lambda: _fake)

    _seed(client)
    h1 = {"Content-Type": "application/json", "X-Idempotency-Key": "removetest-1"}
    r1 = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": True},
        headers=h1,
    )
    assert r1.json()["ok"] is True
    r2 = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": True},
        headers=h1,
    )
    assert r2.status_code == 200
    assert r2.json() == r1.json()


def test_remove_unknown_client_is_noop_ok_false(client):
    # Nothing seeded for this client -> ok False but no crash.
    r = client.post(
        "/api/admin/clients/0000000000000/remove-customer",
        json={"confirm": True},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_remove_by_billing_alias_resolves_to_canonical_id(client):
    """A billing/invoice id must remove the SAME customer as the marketing id.

    Regression: every derived store (brand kit, blogs, crm, content queue,
    clients record) is keyed on the canonical marketing id. Passing an invoice
    alias used to delete nothing while still returning a summary, leaving a
    half-removed customer who keeps receiving content and counting as active.
    """
    alias = "d79d690f61b3"  # pragma: allowlist secret - billing client id, not a credential
    _seed(client, clients=False)
    clients_store._append(
        {
            "id": CID,
            "business_name": "Estique Salon & Spa",
            "niche": "beauty_salon",
            "phone": "+919812345678",
            "status": "active",
            "product": "marketing",
            "billing_client_ids": [alias],
            "created_at": "2026-08-01T00:00:00+00:00",
        }
    )

    r = client.post(
        "/api/admin/clients/" + alias + "/remove-customer",
        json={"confirm": True, "reason": "alias path"},
    )
    assert r.status_code == 200
    d = r.json()

    # Resolved to the canonical id, and reported both for operator traceability.
    assert d["client_id"] == CID
    assert d["requested_client_id"] == alias

    # The canonical-keyed stores actually got cleaned, not silently skipped.
    assert d["ok"] is True
    assert d["clients_record_deleted"] is True
    assert d["brand_kit_deleted"] is True
    assert d["content_cancelled"] == 3
    assert clients_store.get_client(CID) is None
