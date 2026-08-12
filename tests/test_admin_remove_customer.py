"""Admin customer removal — soft-disable default + owner-gated purge.

Covers: confirm-required gate, soft status=cancelled (ledgers kept), purge
gates (confirm_purge + ADMIN_CUSTOMER_PURGE_ENABLED), portal-login revoke,
content-schedule cancel, autopilot prospect -> terminal removed, brand-kit +
derived store file deletion (purge only), clients_store record deletion
(purge only), idempotency replay, audit.
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
    # Purge fail-closed by default in every test unless a case arms it.
    monkeypatch.delenv("ADMIN_CUSTOMER_PURGE_ENABLED", raising=False)

    monkeypatch.delenv("SALES_AUTOPILOT_ENABLED", raising=False)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _purge_json(**extra):
    body = {"confirm": True, "mode": "purge", "confirm_purge": True}
    body.update(extra)
    return body


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
                date_iso=f"2026-08-{10 + i:02d}",
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


def test_soft_disable_default_keeps_ledgers(client):
    """Default mode=soft: cancel + disable, keep brand kit / derived files."""
    _seed(client)
    r = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": True, "reason": "churn soft"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["mode"] == "soft"
    assert d["auth_logins_revoked"] == 1
    assert d["content_cancelled"] == 3
    assert d["prospects_removed"] == 1
    assert d["client_status_set"] is True
    assert d["brand_kit_deleted"] is False
    assert d["delivery_deleted"] is False
    assert d["clients_record_deleted"] is False

    from app.api import customer_auth

    assert customer_auth.client_has_login(CID) is False
    rec = clients_store.get_client(CID)
    assert rec is not None
    assert rec.get("status") == "cancelled"
    assert os.path.exists(product_one_delivery._events_path(CID))
    assert os.path.exists(str(client_blog._path(CID)))
    assert os.path.exists(crm_lite._path(CID))
    assert brand_kit.get_brand(CID) is not None


def test_purge_refused_without_confirm_purge(client, monkeypatch):
    monkeypatch.setenv("ADMIN_CUSTOMER_PURGE_ENABLED", "1")
    _seed(client)
    r = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": True, "mode": "purge"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "confirm_purge" in r.json()["error"]


def test_purge_refused_when_env_disarmed(client):
    _seed(client)
    r = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json=_purge_json(reason="should refuse"),
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "purge disabled" in r.json()["error"]


def test_remove_customer_full_cleanup(client, monkeypatch):
    monkeypatch.setenv("ADMIN_CUSTOMER_PURGE_ENABLED", "1")
    _seed(client)
    r = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json=_purge_json(reason="not a real customer"),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["mode"] == "purge"
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

    _fake = _FakeRedis()
    monkeypatch.setattr(idem, "_redis", lambda: _fake)

    _seed(client)
    h1 = {"Content-Type": "application/json", "X-Idempotency-Key": "removetest-1"}
    r1 = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": True, "mode": "soft"},
        headers=h1,
    )
    assert r1.json()["ok"] is True
    r2 = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": True, "mode": "soft"},
        headers=h1,
    )
    assert r2.status_code == 200
    assert r2.json() == r1.json()


def test_remove_unknown_client_is_noop_ok_false(client):
    r = client.post(
        "/api/admin/clients/0000000000000/remove-customer",
        json={"confirm": True},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_remove_by_billing_alias_resolves_to_canonical_id(client, monkeypatch):
    monkeypatch.setenv("ADMIN_CUSTOMER_PURGE_ENABLED", "1")
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
        json=_purge_json(reason="alias path"),
    )
    assert r.status_code == 200
    d = r.json()

    assert d["client_id"] == CID
    assert d["requested_client_id"] == alias
    assert d["ok"] is True
    assert d["clients_record_deleted"] is True
    assert d["brand_kit_deleted"] is True
    assert d["content_cancelled"] == 3
    assert clients_store.get_client(CID) is None


def test_remove_customer_cancels_billing_subscription(client, db):
    """MRR truth: soft-disable must CANCEL the DB Subscription row."""
    from app.models.payment import Subscription, SubscriptionStatus
    from tests.conftest import TestingSessionLocal

    _seed(client)

    with TestingSessionLocal() as s:
        s.add(
            Subscription(
                id="sub_rm_1",
                client_id=CID,
                plan_id="starter",
                plan_name="Starter",
                status=SubscriptionStatus.ACTIVE,
                base_price=1999,
            )
        )
        s.commit()

    r = client.post(
        "/api/admin/clients/" + CID + "/remove-customer",
        json={"confirm": True, "reason": "churn test"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "soft"
    assert d["subscriptions_cancelled"] == 1
    assert d["subscription_ids"] == ["sub_rm_1"]

    with TestingSessionLocal() as s:
        sub = s.query(Subscription).filter(Subscription.id == "sub_rm_1").one()
        assert sub.status == SubscriptionStatus.CANCELLED
        assert sub.cancel_reason == "churn test"
        assert sub.cancelled_at is not None


def test_remove_customer_cancels_alias_and_trial_subscriptions(client, db):
    """Alias-owned + TRIAL Subscription rows must cancel too (real Jiya shape)."""
    from app.models.payment import Subscription, SubscriptionStatus
    from tests.conftest import TestingSessionLocal

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
        }
    )

    with TestingSessionLocal() as s:
        s.add_all(
            [
                Subscription(
                    id="sub_alias_1",
                    client_id=alias,
                    plan_id="starter",
                    plan_name="Starter",
                    status=SubscriptionStatus.ACTIVE,
                    base_price=1999,
                ),
                Subscription(
                    id="sub_trial_1",
                    client_id=CID,
                    plan_id="starter",
                    plan_name="Starter",
                    status=SubscriptionStatus.TRIAL,
                    base_price=0,
                ),
            ]
        )
        s.commit()

    r = client.post(
        "/api/admin/clients/" + alias + "/remove-customer",
        json={"confirm": True, "reason": "alias churn"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["subscriptions_cancelled"] == 2
    assert set(d["subscription_ids"]) == {"sub_alias_1", "sub_trial_1"}

    with TestingSessionLocal() as s:
        for sid in ("sub_alias_1", "sub_trial_1"):
            sub = s.query(Subscription).filter(Subscription.id == sid).one()
            assert sub.status == SubscriptionStatus.CANCELLED
