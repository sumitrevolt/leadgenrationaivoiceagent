"""RED-first: lead_alerts owner ntfy push (speed-to-lead phone alert).

Naya lead aate hi platform owner ke PHONE pe ntfy buzz (email complement) with a
1-tap WhatsApp action. Gated LEAD_NTFY_ALERT (default ON) + ntfy.enabled()
(NTFY_URL+NTFY_TOPIC). Alert flow ko KABHI nahi todta; email/client-WA paths
unaffected. Mirrors tests/test_content_ordering_lead_alerts.py conventions.
"""

from __future__ import annotations

import asyncio


def _isolate_email_wa(monkeypatch, lead_alerts):
    """Email + client-WA channels off — ntfy path ko isolate karo."""
    monkeypatch.setattr(lead_alerts, "_notify_email_to", lambda: "")
    monkeypatch.setattr(lead_alerts, "_lookup_client", lambda rec: {})


def test_owner_ntfy_push_fires_when_armed(tmp_path, monkeypatch):
    from app.integrations import ntfy
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("LEAD_NTFY_ALERT", "1")
    monkeypatch.setattr(ntfy, "enabled", lambda: True)
    _isolate_email_wa(monkeypatch, lead_alerts)

    calls: list[dict] = []

    async def fake_push(title, message, priority="default", tags=None, actions=None):
        calls.append(
            {"title": title, "message": message, "priority": priority, "actions": actions or []}
        )
        return True

    monkeypatch.setattr(ntfy, "push", fake_push)

    res = asyncio.run(
        lead_alerts.notify_new_lead({"name": "Ravi", "phone": "9876543210", "niche": "solar"})
    )
    assert res["ok"] is True
    assert res["push_sent"] is True
    assert len(calls) == 1
    assert "Ravi" in calls[0]["title"]
    assert "9876543210" in calls[0]["message"]
    assert calls[0]["priority"] == "high"
    # 1-tap WhatsApp action seedha lead ko
    labels = [a.get("label") for a in calls[0]["actions"]]
    assert "WhatsApp" in labels
    assert any("wa.me/919876543210" in (a.get("url") or "") for a in calls[0]["actions"])


def test_owner_ntfy_flag_off_no_push(tmp_path, monkeypatch):
    from app.integrations import ntfy
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("LEAD_NTFY_ALERT", "0")  # OFF
    monkeypatch.setattr(ntfy, "enabled", lambda: True)
    _isolate_email_wa(monkeypatch, lead_alerts)

    calls: list[int] = []

    async def fake_push(*a, **k):
        calls.append(1)
        return True

    monkeypatch.setattr(ntfy, "push", fake_push)

    res = asyncio.run(lead_alerts.notify_new_lead({"name": "A", "phone": "9812345678"}))
    assert res["push_sent"] is False
    assert len(calls) == 0  # flag OFF → push kabhi call nahi hua


def test_owner_ntfy_inert_when_ntfy_disabled(tmp_path, monkeypatch):
    from app.integrations import ntfy
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("LEAD_NTFY_ALERT", "1")
    monkeypatch.setattr(ntfy, "enabled", lambda: False)  # NTFY_URL/TOPIC unset
    _isolate_email_wa(monkeypatch, lead_alerts)

    calls: list[int] = []

    async def fake_push(*a, **k):
        calls.append(1)
        return True

    monkeypatch.setattr(ntfy, "push", fake_push)

    res = asyncio.run(lead_alerts.notify_new_lead({"name": "B", "phone": "9800000000"}))
    assert res["ok"] is True
    assert res["push_sent"] is False
    assert len(calls) == 0  # inert — push touch nahi hua


def test_owner_ntfy_never_raises_on_push_error(tmp_path, monkeypatch):
    from app.integrations import ntfy
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("LEAD_NTFY_ALERT", "1")
    monkeypatch.setattr(ntfy, "enabled", lambda: True)
    _isolate_email_wa(monkeypatch, lead_alerts)

    async def boom(*a, **k):
        raise RuntimeError("ntfy down")

    monkeypatch.setattr(ntfy, "push", boom)

    res = asyncio.run(lead_alerts.notify_new_lead({"name": "C", "phone": "9700000000"}))
    # flow survive kare; push_sent False; koi exception nahi
    assert res["ok"] is True
    assert res["push_sent"] is False


def test_owner_ntfy_no_wa_action_when_phone_short(tmp_path, monkeypatch):
    from app.integrations import ntfy
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setenv("LEAD_NTFY_ALERT", "1")
    monkeypatch.setattr(ntfy, "enabled", lambda: True)
    _isolate_email_wa(monkeypatch, lead_alerts)

    calls: list[dict] = []

    async def fake_push(title, message, priority="default", tags=None, actions=None):
        calls.append({"actions": actions or []})
        return True

    monkeypatch.setattr(ntfy, "push", fake_push)

    # phone digits < 10 → WhatsApp action skip, par Dashboard action rahe
    res = asyncio.run(lead_alerts.notify_new_lead({"name": "NoPhone", "phone": "123"}))
    assert res["push_sent"] is True
    labels = [a.get("label") for a in calls[0]["actions"]]
    assert "WhatsApp" not in labels
    assert "Dashboard" in labels
