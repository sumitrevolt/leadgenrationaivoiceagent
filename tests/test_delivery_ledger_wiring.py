"""Each of these tests monkeypatches app.platform.delivery_ledger.log_event at
the call site and asserts it fires with the right event_type/client_id — the
same style already used in tests/test_call_event_client_id.py for
app.platform.team.log_event."""

import pytest


def test_add_client_logs_customer_created(monkeypatch, tmp_path):
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", str(tmp_path / "clients.jsonl"))
    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )
    rec = clients_store.add_client(business_name="Test Biz", niche="solar", phone="9812345678")
    assert rec.get("id")
    assert (rec["id"], "customer_created") in events


def test_activate_plan_logs_plan_activated(monkeypatch):
    from app.billing import usage

    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: {"id": cid, "business_name": "Test Biz"},
        raising=False,
    )
    monkeypatch.setattr("app.marketing.clients_store.update_client", lambda cid, **kw: None, raising=False)
    # Subscription-row side of activate_plan touches the DB — irrelevant to this
    # test, so make it a no-op rather than requiring a live DB.
    monkeypatch.setattr(usage, "_latest_subscription", lambda db, cid: None, raising=False)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )
    usage.activate_plan("client_abc", "starter")
    assert ("client_abc", "plan_activated") in events


@pytest.mark.asyncio
async def test_auto_onboard_logs_started_and_completed(monkeypatch):
    from app.marketing import onboarding

    client = {"id": "c1", "business_name": "Test Biz"}
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: client, raising=False)
    monkeypatch.setattr("app.marketing.clients_store.update_client", lambda cid, **kw: None, raising=False)

    async def _fake_seed_kb(cid, website):
        return {"kb_chunks": 0}

    async def _fake_content_pack(client):
        return {"ok": True}

    async def _fake_welcome(client, kb_seeded):
        return {"sent": False}

    monkeypatch.setattr(onboarding, "_seed_kb_from_website", _fake_seed_kb)
    monkeypatch.setattr(onboarding, "_first_content_pack", _fake_content_pack)
    monkeypatch.setattr(onboarding, "_send_welcome_whatsapp", _fake_welcome)
    monkeypatch.setattr("app.marketing.auto_content.seed_client_content", lambda client: _async_zero(), raising=False)
    monkeypatch.setattr("app.platform.client_snapshots.apply_niche_to_client", lambda cid: {"ok": True}, raising=False)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )

    await onboarding.auto_onboard("c1")
    kinds = [e[1] for e in events if e[0] == "c1"]
    assert "onboarding_started" in kinds
    assert "onboarding_completed" in kinds
    assert kinds.index("onboarding_started") < kinds.index("onboarding_completed")


async def _async_zero():
    return 0


@pytest.mark.asyncio
async def test_seed_client_content_logs_calendar_and_drafts(monkeypatch):
    from app.marketing import auto_content

    async def _fake_generate(client):
        return [{"type": "post"}, {"type": "post"}]

    monkeypatch.setattr(auto_content, "generate_for_client", _fake_generate)
    monkeypatch.setattr(auto_content, "_append_items", lambda cid, items: len(items), raising=False)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type, kw.get("meta"))),
    )

    added = await auto_content.seed_client_content({"id": "c1", "business_name": "Test Biz"})
    assert added == 2
    kinds = [e[1] for e in events if e[0] == "c1"]
    assert "marketing_calendar_generated" in kinds
    assert "post_draft_created" in kinds
    draft_event = next(e for e in events if e[1] == "post_draft_created")
    assert draft_event[2].get("count") == 2


@pytest.mark.asyncio
async def test_seed_client_content_no_ledger_noise_when_zero_added(monkeypatch):
    """Zero new drafts (dedupe hit / recycle also empty) -> no misleading events."""
    from app.marketing import auto_content

    async def _fake_generate(client):
        return []

    monkeypatch.setattr(auto_content, "generate_for_client", _fake_generate)
    monkeypatch.setattr(auto_content, "_append_items", lambda cid, items: 0, raising=False)

    async def _fake_recycle(client):
        return 0

    monkeypatch.setattr(auto_content, "_recycle_fallback", _fake_recycle)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )
    added = await auto_content.seed_client_content({"id": "c1", "business_name": "Test Biz"})
    assert added == 0
    assert events == []
