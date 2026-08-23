"""Tests for the P0 customer value-delivery guarantee (2026-07-05 council fix):
value-first delivery, paid detection, mini-site URL, dead-man detector, and the
AUTO_DELIVER_VALUE gate. Offline (no WhatsApp send).
"""

import os

import pytest

from app.marketing import customer_delivery as cd


def test_is_paid_client():
    assert cd.is_paid_client({"status": "active", "plan": "starter"}) is True
    assert cd.is_paid_client({"status": "active", "plan": "advanced"}) is True
    assert cd.is_paid_client({"status": "active", "plan": "trial"}) is False
    assert cd.is_paid_client({"status": "active", "plan": ""}) is False
    assert cd.is_paid_client({"status": "paused", "plan": "starter"}) is False
    # self-brand entries are NOT delivery targets (company's own record)
    assert (
        cd.is_paid_client({"status": "active", "plan": "starter", "id": "leadgenai-self"}) is False
    )
    assert (
        cd.is_paid_client({"status": "active", "plan": "growth", "business_name": "LeadGen AI"})
        is False
    )
    assert (
        cd.is_paid_client({"status": "active", "plan": "starter", "niche": "ai_marketing"}) is False
    )


def test_payment_evidence_is_tri_state(monkeypatch):
    """Plan is chosen pre-payment, so only an immutable invoice proves payment.
    An unreadable/empty ledger must stay UNKNOWN (None) -> callers fail-OPEN.
    """
    from app.billing import gst_invoice

    # Ledger with real content = authoritative judgement.
    monkeypatch.setattr(gst_invoice, "_read", lambda: [{"client_id": "d79d690f61b3"}])
    assert cd._payment_evidence({"id": "d79d690f61b3"}) is True
    assert cd._payment_evidence({"id": "1f89031d621a"}) is False
    # Legacy/recreated identity keeps invoice ownership via billing_client_ids.
    assert (
        cd._payment_evidence({"id": "jiya-makeover", "billing_client_ids": ["d79d690f61b3"]})
        is True
    )

    # Empty ledger = anomaly, NOT proof of non-payment -> UNKNOWN.
    monkeypatch.setattr(gst_invoice, "_read", lambda: [])
    assert cd._payment_evidence({"id": "d79d690f61b3"}) is None

    # Unreadable ledger -> UNKNOWN (never raises).
    def _boom():
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(gst_invoice, "_read", _boom)
    assert cd._payment_evidence({"id": "d79d690f61b3"}) is None
    assert cd._payment_evidence({}) is None


def test_has_paid_evidence_excludes_never_invoiced_tenant(monkeypatch):
    """Regression: synthetic 'Test Biz' (plan=growth, zero invoices) was paging the
    founder hourly as a ghosted PAID customer. Mirrors the real prod truth table
    (invoice ledger holds exactly one row: jiya's d79d690f61b3).
    """
    from app.billing import gst_invoice

    monkeypatch.setattr(gst_invoice, "_read", lambda: [{"client_id": "d79d690f61b3"}])

    jiya = {
        "id": "jiya-makeover",
        "status": "active",
        "plan": "starter",
        "billing_client_ids": ["d79d690f61b3"],
    }
    test_biz = {"id": "1f89031d621a", "status": "active", "plan": "growth"}

    # Eligibility (plan) is unchanged for both...
    assert cd.is_paid_client(jiya) is True
    assert cd.is_paid_client(test_biz) is True
    # ...but only the invoiced identity has real payment evidence.
    assert cd.has_paid_evidence(jiya) is True
    assert cd.has_paid_evidence(test_biz) is False


def test_has_paid_evidence_fails_open_when_ledger_unavailable(monkeypatch):
    """A broken/empty invoice ledger must NEVER silently drop a real paying customer
    from the dead-man detector — that is the ghosting incident this module prevents.
    """
    from app.billing import gst_invoice

    monkeypatch.setattr(gst_invoice, "_read", lambda: [])
    assert (
        cd.has_paid_evidence({"id": "jiya-makeover", "status": "active", "plan": "starter"}) is True
    )

    def _boom():
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(gst_invoice, "_read", _boom)
    assert (
        cd.has_paid_evidence({"id": "jiya-makeover", "status": "active", "plan": "starter"}) is True
    )
    # ...but a trial/placeholder plan is still never "paid".
    assert cd.has_paid_evidence({"id": "x", "status": "active", "plan": "trial"}) is False


def test_find_undelivered_paid_clients_ignores_never_invoiced_tenant(monkeypatch):
    """End-to-end for the alert source: the dead-man detector must not surface a
    never-invoiced tenant (this is what reached _record_stuck -> ops_alerts hourly).
    """
    from app.billing import gst_invoice

    monkeypatch.setattr(gst_invoice, "_read", lambda: [{"client_id": "d79d690f61b3"}])
    clients = [
        {
            "id": "jiya-makeover",
            "status": "active",
            "plan": "starter",
            "billing_client_ids": ["d79d690f61b3"],
        },
        {"id": "1f89031d621a", "status": "active", "plan": "growth"},
    ]
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None: [c for c in clients if (status is None or c["status"] == status)],
        raising=False,
    )
    ids = {c["id"] for c in cd.find_undelivered_paid_clients()}
    assert ids == {"jiya-makeover"}


def test_mini_site_url():
    assert cd.mini_site_url({"slug": "jiya-makeover-d79d"}).endswith("/b/jiya-makeover-d79d")
    assert cd.mini_site_url({"slug": ""}) == ""
    assert cd.mini_site_url({}) == ""


def test_is_delivered():
    assert cd.is_delivered({"delivery_state": "delivered"}) is True
    assert cd.is_delivered({"delivery_state": "acknowledged"}) is True
    assert cd.is_delivered({"delivery_state": "paid"}) is False
    assert cd.is_delivered({}) is False


def test_build_delivery_message_is_value_first():
    """Message must hand over the LIVE mini-site link — value-first, not an info-ask."""
    msg = cd.build_delivery_message(
        {"business_name": "jiya makeover", "slug": "jiya-makeover-d79d"}
    )
    assert "jiya makeover" in msg
    assert "/b/jiya-makeover-d79d" in msg
    # must NOT be the old "describe your business first" gate
    assert "kya services dete hain" not in msg.lower()


@pytest.mark.asyncio
async def test_deliver_gated_off_by_default(monkeypatch):
    """With AUTO_DELIVER_VALUE unset, deliver must NOT send (records stuck instead)."""
    monkeypatch.delenv("AUTO_DELIVER_VALUE", raising=False)
    sent = {"called": False}

    class _FakeSender:
        async def send_text_message(self, to, msg):
            sent["called"] = True
            return {"ok": True}

    monkeypatch.setattr(
        "app.integrations.whatsapp.get_whatsapp_sender", lambda: _FakeSender(), raising=False
    )
    r = await cd.deliver_client_value(
        {"id": "x1", "status": "active", "plan": "starter", "slug": "s", "phone": "9812345678"}
    )
    assert r["delivered"] is False
    assert r.get("skipped") == "AUTO_DELIVER_VALUE off"
    assert sent["called"] is False  # gate held — no customer message sent


@pytest.mark.asyncio
async def test_stuck_customer_pages_founder_not_just_a_logfile(monkeypatch):
    """The jiya-makeover-class ghosting bug: a stuck paid customer must page the
    founder via ops_alerts, not just append a jsonl line nobody is watching.
    Regression guard for the 2026-07 fix wiring _record_stuck -> ops_alerts."""
    monkeypatch.delenv("AUTO_DELIVER_VALUE", raising=False)
    paged: list[tuple] = []
    monkeypatch.setattr(
        "app.platform.ops_alerts.alert_paid_customer_stuck",
        lambda cid, name, reason: paged.append((cid, name, reason)),
        raising=False,
    )
    r = await cd.deliver_client_value(
        {
            "id": "x1",
            "status": "active",
            "plan": "starter",
            "slug": "s",
            "phone": "9812345678",
            "business_name": "jiya makeover",
        }
    )
    assert r["delivered"] is False
    assert len(paged) == 1
    cid, name, reason = paged[0]
    assert cid == "x1"
    assert name == "jiya makeover"
    assert reason == "auto_delivery_off"


@pytest.mark.asyncio
async def test_deliver_force_sends_and_marks(monkeypatch):
    """force=True (operator single-send) sends + marks delivered."""
    marked = {}

    class _FakeSender:
        async def send_text_message(self, to, msg):
            return {"ok": True}

    monkeypatch.setattr(
        "app.integrations.whatsapp.get_whatsapp_sender", lambda: _FakeSender(), raising=False
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.update_client",
        lambda cid, **kw: marked.update({"cid": cid, **kw}),
        raising=False,
    )
    r = await cd.deliver_client_value(
        {"id": "x2", "status": "active", "plan": "starter", "slug": "s", "phone": "9812345678"},
        force=True,
    )
    assert r["delivered"] is True
    assert marked.get("delivery_state") == "delivered"
    assert marked.get("delivered_at")


def test_activation_and_acknowledgment(monkeypatch):
    """A delivered paid customer's inbound reply flips delivery_state->acknowledged
    (council: 'delivered = acknowledged'); non-delivered/non-paid unaffected."""
    marked = {}
    clients = [
        {
            "id": "j",
            "status": "active",
            "plan": "starter",
            "phone": "918712928847",
            "delivery_state": "delivered",
        },  # delivered paid -> should ack
        {
            "id": "t",
            "status": "active",
            "plan": "trial",
            "phone": "9800000000",
            "delivery_state": "delivered",
        },  # not paid -> ignore
    ]
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None: clients,
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.update_client",
        lambda cid, **kw: marked.update({"cid": cid, **kw}),
        raising=False,
    )
    # reply from jiya's number (with country code) — last-10 match
    assert cd.try_mark_acknowledged("918712928847@c.us") is True
    assert marked.get("cid") == "j"
    assert marked.get("delivery_state") == "acknowledged"
    assert cd.is_activated({"delivery_state": "acknowledged"}) is True
    assert cd.is_activated({"delivery_state": "delivered"}) is False


def test_ack_ignores_unknown_number(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None: [
            {
                "id": "j",
                "status": "active",
                "plan": "starter",
                "phone": "918712928847",
                "delivery_state": "delivered",
            }
        ],
        raising=False,
    )
    assert cd.try_mark_acknowledged("919999999999") is False


def test_build_weekly_digest_honest(monkeypatch):
    """Digest includes the REAL fresh_count + mini-site link; never invents views/leads."""
    c = {"business_name": "jiya makeover", "slug": "jiya-makeover-d79d"}
    msg = cd.build_weekly_digest_message(c, 5)
    assert "5 naye" in msg
    assert "/b/jiya-makeover-d79d" in msg
    # honesty: no fabricated view/lead numbers
    assert "views" not in msg.lower()
    # zero fresh content -> graceful, no "0 naye"
    msg0 = cd.build_weekly_digest_message(c, 0)
    assert "0 naye" not in msg0


def test_monthly_receipt_honest_metrics():
    """Monthly receipt shows only REAL views + content; no fabricated numbers."""
    c = {"business_name": "jiya makeover", "slug": "jiya-makeover-d79d"}
    msg = cd.build_monthly_receipt_message(c, views=12, content=8)
    assert "12 baar" in msg and "8 naye" in msg
    assert "/b/jiya-makeover-d79d" in msg
    # zero-data path is graceful (no "0 baar")
    msg0 = cd.build_monthly_receipt_message(c, views=0, content=0)
    assert "0 baar" not in msg0


def test_referral_line_only_when_configured(monkeypatch):
    c = {"business_name": "x", "slug": "s"}
    monkeypatch.delenv("REFERRAL_REWARD", raising=False)
    assert "refer" not in cd.build_monthly_receipt_message(c, 5, 5).lower()
    monkeypatch.setenv("REFERRAL_REWARD", "1 mahina free")
    assert "1 mahina free" in cd.build_monthly_receipt_message(c, 5, 5)


def test_case_study_is_honest(monkeypatch):
    """Case study uses REAL assets; testimonial only if actually present."""
    cs1 = cd.build_case_study(
        {
            "id": "j",
            "business_name": "jiya makeover",
            "slug": "jiya-makeover-d79d",
            "niche": "beauty",
        }
    )
    assert cs1["has_testimonial"] is False
    assert any("/b/jiya-makeover-d79d" in p for p in cs1["proof_points"])
    cs2 = cd.build_case_study(
        {"id": "j", "business_name": "jiya", "slug": "s", "testimonial": "Bahut accha kaam!"}
    )
    assert cs2["has_testimonial"] is True
    assert any("Bahut accha" in p for p in cs2["proof_points"])


@pytest.mark.asyncio
async def test_growth_sweeps_gated_off(monkeypatch):
    monkeypatch.delenv("AUTO_DELIVER_VALUE", raising=False)
    assert (await cd.run_monthly_receipt_sweep()).get("skipped") == "AUTO_DELIVER_VALUE off"
    assert (await cd.run_testimonial_sweep()).get("skipped") == "flag off"


def test_digest_due_cadence():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    assert cd._digest_due("new", {}, now) is True  # never sent -> due
    recent = {"x": (now - timedelta(days=2)).isoformat()}
    assert cd._digest_due("x", recent, now) is False  # 2 days ago -> not due
    old = {"x": (now - timedelta(days=8)).isoformat()}
    assert cd._digest_due("x", old, now) is True  # 8 days ago -> due


@pytest.mark.asyncio
async def test_weekly_digest_gated_off(monkeypatch):
    monkeypatch.delenv("AUTO_DELIVER_VALUE", raising=False)
    r = await cd.run_weekly_digest_sweep()
    assert r.get("skipped") == "AUTO_DELIVER_VALUE off"


@pytest.mark.asyncio
async def test_find_undelivered_paid_clients(monkeypatch):
    # Pin the invoice ledger to UNKNOWN (fail-OPEN) so this case stays hermetic and
    # keeps testing exactly what it means to: the plan/status/delivered filtering.
    # Payment-evidence gating has its own dedicated cases above.
    from app.billing import gst_invoice

    monkeypatch.setattr(gst_invoice, "_read", lambda: [])
    clients = [
        {"id": "a", "status": "active", "plan": "starter"},  # undelivered paid -> included
        {"id": "b", "status": "active", "plan": "starter", "delivery_state": "delivered"},  # done
        {"id": "c", "status": "active", "plan": "trial"},  # not paid
        {"id": "d", "status": "paused", "plan": "starter"},  # not active
    ]
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None: [c for c in clients if (status is None or c["status"] == status)],
        raising=False,
    )
    out = cd.find_undelivered_paid_clients()
    ids = {c["id"] for c in out}
    assert ids == {"a"}
