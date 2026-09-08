"""client_id attribution on call events (2026-07-02, P2-3).

Fixes a real gap found while wiring metadata for _calls_from_events: a mini-site
inquiry's auto-callback call never threaded client_id through to
start_stream_call — so the call greeted as generic "Demo Co"/"LeadGen AI"
instead of the actual business, skipped KB grounding (TelecallerBrain scopes
RAG by client_id), never appeared in that client's own CallLog/dashboard, and
skipped auto-qualify->CRM/sales downstream wiring (gated on `self.client_id`
in vobiz_stream.py). Also found + fixed: missed_call.py was passing `business`
into start_stream_call's 3rd POSITIONAL param, which is `client_id`, not a
display name — a pre-existing bug in a flag-gated-OFF feature.

Covers:
  - app/api/public_site.py::_auto_callback — client_id threaded to
    start_stream_call + into the "auto_callback" AgentEvent meta.
  - app/platform/inquiry_hooks.py::run_after_inquiry — passes the already-
    resolved `cid` (mini_client_id or rec['client_id']) through.
  - app/telephony/missed_call.py::handle_missed_call — no longer stuffs
    `business` into client_id.
  - app/api/telephony_vobiz.py "call_placed" + app/telephony/vobiz_stream.py
    "call_finished" AgentEvent meta now carry client_id.
"""

from __future__ import annotations

import asyncio


def test_auto_callback_threads_client_id_to_start_stream_call(monkeypatch):
    import app.api.public_site as ps

    captured = {}

    async def _fake_start_stream_call(
        to,
        niche="general",
        client_id=None,
        call_type="transactional",
        opening_line="",
        dry_run=False,
    ):
        captured.update(to=to, niche=niche, client_id=client_id)
        return {"placed": True, "stream_token": "tok123"}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start_stream_call)

    events = []
    monkeypatch.setattr(
        "app.platform.team.log_event",
        lambda member, action, detail, status="ok", meta=None: events.append(
            {"member": member, "action": action, "meta": meta or {}}
        ),
    )

    asyncio.run(ps._auto_callback("9876543210", "salon", "Sharma Salon", client_id="client_abc"))

    assert captured["client_id"] == "client_abc"
    assert events and events[0]["meta"].get("client_id") == "client_abc"


def test_auto_callback_platform_lead_stays_client_id_none(monkeypatch):
    """A platform-level lead (no paying client yet) must NOT get a fabricated
    client_id — client_id="" must resolve to None, unchanged behaviour."""
    import app.api.public_site as ps

    captured = {}

    async def _fake_start_stream_call(
        to,
        niche="general",
        client_id=None,
        call_type="transactional",
        opening_line="",
        dry_run=False,
    ):
        captured.update(client_id=client_id)
        return {"placed": True}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start_stream_call)
    monkeypatch.setattr("app.platform.team.log_event", lambda *a, **k: None)

    asyncio.run(ps._auto_callback("9876543210", "general", "Some Lead"))
    assert captured["client_id"] is None


def test_run_after_inquiry_passes_resolved_client_id_to_auto_callback(monkeypatch):
    import app.platform.inquiry_hooks as ih

    captured = {}

    async def _fake_auto_callback(
        phone, niche, business, client_id="", opening_line="", dry_run=False
    ):
        captured.update(phone=phone, niche=niche, business=business, client_id=client_id)

    monkeypatch.setattr("app.api.public_site._auto_callback", _fake_auto_callback)
    # Silence unrelated best-effort hooks inside run_after_inquiry so this test
    # stays focused on the auto-callback wiring only.
    monkeypatch.setattr(
        "app.platform.sales_qualify.bant_score",
        lambda rec: {"grade": "C", "total": 50, "action": ""},
    )
    monkeypatch.setattr("app.platform.lead_alerts.notify_new_lead_bg", lambda rec: None)

    rec = {
        "phone": "9998887777",
        "niche": "salon",
        "business_name": "Test Biz",
        "client_id": "client_from_rec",
    }
    asyncio.run(ih.run_after_inquiry(rec))

    assert captured.get("client_id") == "client_from_rec"


def test_run_after_inquiry_mini_client_id_overrides_rec_client_id(monkeypatch):
    """mini_client_id (the mini-site owner) takes precedence over any client_id
    embedded in the raw inquiry payload — same precedence already used for the
    customer_webhooks hook a few lines below in run_after_inquiry."""
    import app.platform.inquiry_hooks as ih

    captured = {}

    async def _fake_auto_callback(
        phone, niche, business, client_id="", opening_line="", dry_run=False
    ):
        captured.update(client_id=client_id)

    monkeypatch.setattr("app.api.public_site._auto_callback", _fake_auto_callback)
    monkeypatch.setattr(
        "app.platform.sales_qualify.bant_score",
        lambda rec: {"grade": "C", "total": 50, "action": ""},
    )
    monkeypatch.setattr("app.platform.lead_alerts.notify_new_lead_bg", lambda rec: None)

    rec = {"phone": "9998887777", "niche": "salon", "client_id": "wrong_id"}
    asyncio.run(ih.run_after_inquiry(rec, mini_client_id="mini_owner_id"))

    assert captured.get("client_id") == "mini_owner_id"


def test_missed_call_no_longer_misuses_business_as_client_id(monkeypatch):
    """Regression: previously `starter(num, niche, business)` positionally put
    `business` into start_stream_call's client_id param. Must call with explicit
    keywords now — client_id must never be the free-text business string."""
    import app.api.public_site as ps
    from app.telephony import missed_call

    monkeypatch.setattr(ps, "_append_jsonl", lambda r: True, raising=False)
    monkeypatch.setattr(ps, "_save_lead_db", lambda r: None, raising=False)
    monkeypatch.setenv("MISSED_CALL_CALLBACK", "1")
    missed_call._RECENT.clear()

    captured = {}

    async def _fake_start_stream_call(
        to,
        niche="general",
        client_id=None,
        call_type="transactional",
        opening_line="",
        dry_run=False,
    ):
        captured.update(to=to, niche=niche, client_id=client_id, call_type=call_type)
        return {"placed": True}

    import app.api.telephony_vobiz as tv

    monkeypatch.setattr(tv, "start_stream_call", _fake_start_stream_call)

    res = asyncio.run(missed_call.handle_missed_call("+919812340000", "solar", "Acme Solar"))
    assert res["ok"] is True and res["callback"] is True
    assert captured["client_id"] is None, "must not stuff business text into client_id"
    assert captured["niche"] == "solar"
    assert captured["call_type"] == "transactional"


def test_call_placed_event_carries_client_id(monkeypatch):
    """app/api/telephony_vobiz.py stream_call route logs 'call_placed' with
    client_id in meta (was missing meta entirely before)."""
    import inspect

    import app.api.telephony_vobiz as tv

    src = inspect.getsource(tv)
    idx = src.index('"call_placed"')
    snippet = src[idx : idx + 300]
    assert "client_id" in snippet


def test_call_finished_event_carries_client_id():
    """app/telephony/vobiz_stream.py _cleanup logs 'call_finished' with
    client_id in meta (was missing before — only stt_counts/duration_s)."""
    import inspect

    import app.telephony.vobiz_stream as vs

    src = inspect.getsource(vs)
    idx = src.index('"call_finished"')
    snippet = src[idx : idx + 400]
    assert "client_id" in snippet
