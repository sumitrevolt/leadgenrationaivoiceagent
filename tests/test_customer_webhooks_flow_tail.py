import asyncio

from app.automation import flow_triggers
from app.platform import customer_webhooks as cw


def test_emit_fires_flow_tail_even_when_customer_webhooks_disabled(monkeypatch):
    monkeypatch.delenv("CUSTOMER_WEBHOOKS", raising=False)  # customer webhooks OFF
    seen = []
    monkeypatch.setattr(
        flow_triggers, "fire_event", lambda et, pl, cid="": seen.append((et, pl, cid))
    )
    r = asyncio.run(cw.emit("c1", "lead.qualified", {"lead_id": "L1"}))
    assert r.get("disabled") is True  # customer-webhook path inert
    assert seen and seen[0][0] == "lead.qualified"  # but flow tail still fired
    assert seen[0][1] == {"lead_id": "L1"} and seen[0][2] == "c1"


def test_emit_never_raises_if_flow_tail_throws(monkeypatch):
    monkeypatch.delenv("CUSTOMER_WEBHOOKS", raising=False)

    def boom(*a, **k):
        raise RuntimeError("flow tail blew up")

    monkeypatch.setattr(flow_triggers, "fire_event", boom)
    r = asyncio.run(cw.emit("c1", "lead.created", {"x": 1}))  # must NOT raise
    assert isinstance(r, dict)
