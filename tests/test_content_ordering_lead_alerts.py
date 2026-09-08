"""Tests for:
(1) auto_content.run_daily_content — PAYING clients pehle process hon,
    LeadGen AI self-brand last (subah content-ready promise customers ko jaldi).
(2) lead_alerts client hot-lead alert — lead record me client_id ho to us CLIENT
    owner ko bhi WA alert (gated CLIENT_HOT_LEAD_ALERT default ON, 1 msg/lead);
    no client_id / no phone → unchanged behaviour.
"""

from __future__ import annotations

import asyncio
import json

import pytest


# --------------------------------------------------------------------------- #
# (1) auto_content ordering — paying client before leadgenai-self
# --------------------------------------------------------------------------- #
def test_run_daily_content_orders_paying_before_self(tmp_path, monkeypatch):
    from app.marketing import auto_content

    # tmp queue dir + no self-seed noise (pure loop).
    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "cq"))
    monkeypatch.setattr(auto_content, "AUTO_SEED_SELF", False)

    # Fake clients_store: self client listed FIRST (arbitrary order), paying last.
    clients = [
        {
            "id": auto_content._SELF_CLIENT_ID,
            "business_name": "LeadGen AI",
            "niche": "ai_marketing",
            "plan": "growth",
            "status": "active",
        },
        {
            "id": "d79d690f61b3",  # pragma: allowlist secret
            "business_name": "Jiya Makeover",
            "niche": "beauty_makeover",
            "plan": "starter",
            "status": "active",
        },
    ]

    class FakeStore:
        def list_clients(self, status=None, product=None):
            return list(clients)

    monkeypatch.setattr(auto_content, "clients_store", FakeStore())

    processed_order: list[str] = []

    async def fake_generate(client, day=None):
        processed_order.append(str(client.get("id")))
        # one deterministic item so it counts as "added"
        # W2.1 caption validator: <10 chars reject hota — valid-length caption do.
        return [
            {
                "id": "x",
                "client_id": str(client.get("id")),
                "date": "2026-07-05",
                "type": "post",
                "title": "t",
                "caption": "aaj ka special offer — abhi call karke jaano",
                "status": "draft",
            }
        ]

    monkeypatch.setattr(auto_content, "generate_for_client", fake_generate)

    res = asyncio.run(auto_content.run_daily_content())
    assert res["clients"] == 2
    # Paying client (jiya) MUST be processed before leadgenai-self.
    assert processed_order[0] == "d79d690f61b3"  # pragma: allowlist secret
    assert processed_order[-1] == auto_content._SELF_CLIENT_ID


def test_content_priority_rank():
    from app.marketing import auto_content

    paying = {"id": "abc", "plan": "starter", "niche": "beauty_makeover"}
    self_c = {"id": auto_content._SELF_CLIENT_ID, "plan": "growth", "niche": "ai_marketing"}
    combo = {"id": "z", "plan": "combo"}
    trial = {"id": "t", "plan": "trial"}

    assert auto_content._content_priority_rank(paying) == 0
    assert auto_content._content_priority_rank(combo) == 0
    assert auto_content._content_priority_rank(self_c) == 1  # self always last
    assert auto_content._content_priority_rank(trial) == 1  # non-paying not prioritized
    assert auto_content._content_priority_rank(None) == 1  # garbage safe


# --------------------------------------------------------------------------- #
# (2) lead_alerts — client owner WA alert
# --------------------------------------------------------------------------- #
class _FakeSender:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_text_message(self, to_number, message):
        self.sent.append((to_number, message))
        return {"ok": True}


def test_client_with_phone_gets_wa_alert(tmp_path, monkeypatch):
    from app.integrations import whatsapp as wa
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("CLIENT_HOT_LEAD_ALERT", "1")
    # email off (isolate WA path)
    monkeypatch.setattr(lead_alerts, "_notify_email_to", lambda: "")

    client = {
        "id": "d79d690f61b3",  # pragma: allowlist secret
        "business_name": "Jiya Makeover",
        "phone": "8712928847",
    }
    monkeypatch.setattr(lead_alerts, "_lookup_client", lambda rec: dict(client))

    fake = _FakeSender()
    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: fake)

    rec = {
        "name": "Ravi",
        "phone": "9876543210",
        "client_id": "d79d690f61b3",  # pragma: allowlist secret
        "lead_id": "L1",
    }
    res = asyncio.run(lead_alerts.notify_new_lead(rec))
    assert res["ok"] is True
    assert res["client_notified"] is True
    # client owner phone got exactly one WA
    assert len(fake.sent) == 1
    assert fake.sent[0][0] == "8712928847"
    assert "Naya lead" in fake.sent[0][1] and "9876543210" in fake.sent[0][1]


def test_client_alert_dedupe_same_lead(tmp_path, monkeypatch):
    from app.integrations import whatsapp as wa
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("CLIENT_HOT_LEAD_ALERT", "1")
    monkeypatch.setattr(lead_alerts, "_notify_email_to", lambda: "")

    client = {"id": "cid1", "business_name": "Biz", "phone": "9111111111"}
    monkeypatch.setattr(lead_alerts, "_lookup_client", lambda rec: dict(client))

    fake = _FakeSender()
    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: fake)

    rec = {"name": "A", "phone": "9222222222", "client_id": "cid1", "lead_id": "L9"}
    asyncio.run(lead_alerts.notify_new_lead(rec))
    # second time same lead → admin phone-dedupe returns early, but even if we call
    # _do_notify directly the client dedupe must hold.
    res2 = asyncio.run(lead_alerts._do_notify(rec))
    assert res2["client_notified"] is False
    assert len(fake.sent) == 1  # no double WA to owner


def test_no_client_id_unchanged(tmp_path, monkeypatch):
    from app.integrations import whatsapp as wa
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("CLIENT_HOT_LEAD_ALERT", "1")
    monkeypatch.setattr(lead_alerts, "_notify_email_to", lambda: "")
    # no client resolved (no client_id)
    monkeypatch.setattr(lead_alerts, "_lookup_client", lambda rec: {})

    fake = _FakeSender()
    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: fake)

    res = asyncio.run(lead_alerts.notify_new_lead({"name": "X", "phone": "9812345678"}))
    assert res["ok"] is True
    assert res["client_notified"] is False
    assert len(fake.sent) == 0  # no WA, unchanged behaviour


def test_client_without_phone_no_wa(tmp_path, monkeypatch):
    from app.integrations import whatsapp as wa
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("CLIENT_HOT_LEAD_ALERT", "1")
    monkeypatch.setattr(lead_alerts, "_notify_email_to", lambda: "")
    # client resolved but NO phone
    monkeypatch.setattr(
        lead_alerts, "_lookup_client", lambda rec: {"id": "c2", "business_name": "NoPhone"}
    )

    fake = _FakeSender()
    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: fake)

    res = asyncio.run(
        lead_alerts.notify_new_lead({"name": "Y", "phone": "9800000000", "client_id": "c2"})
    )
    assert res["client_notified"] is False
    assert len(fake.sent) == 0


def test_client_alert_flag_off(tmp_path, monkeypatch):
    from app.integrations import whatsapp as wa
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("CLIENT_HOT_LEAD_ALERT", "0")  # OFF
    monkeypatch.setattr(lead_alerts, "_notify_email_to", lambda: "")
    monkeypatch.setattr(
        lead_alerts,
        "_lookup_client",
        lambda rec: {"id": "c3", "business_name": "Biz", "phone": "9333333333"},
    )

    fake = _FakeSender()
    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: fake)

    res = asyncio.run(
        lead_alerts.notify_new_lead({"name": "Z", "phone": "9700000000", "client_id": "c3"})
    )
    assert res["client_notified"] is False
    assert len(fake.sent) == 0  # flag OFF → no client WA
