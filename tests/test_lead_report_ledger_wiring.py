"""Customer Delivery OS — final 3 ledger events (Loop 6): lead_captured,
followup_sent, weekly_report_generated.

Covers:
  - app/platform/inquiry_hooks.py::run_after_inquiry — logs lead_captured for
    any client-owned inquiry. Wired here (not submit_inquiry()) because this
    is the SHARED chokepoint for all 4 entry paths (mini-site POST, widget-
    chat, lead-in webhook, WhatsApp Flow) per the module's own docstring —
    wiring only submit_inquiry() would silently miss the other 3.
  - app/api/public_site.py::_auto_callback — logs followup_sent only when the
    AI callback actually placed AND the lead belongs to a paying client
    (platform-level /audit leads have no client to attribute the event to).
  - app/marketing/client_report.py::build_report — logs weekly_report_generated
    on the scheduled/pushed report path (run_monthly's chokepoint), not the
    customer's on-demand view endpoint — logging on-demand would count
    customer-initiated page views as if the AI had "delivered" a report.
"""

from __future__ import annotations

import asyncio


# ---------------------------------------------------------------------------
# lead_captured — app/platform/inquiry_hooks.py::run_after_inquiry
# ---------------------------------------------------------------------------
def _run_hook(rec, monkeypatch, **kw):
    from app.platform import inquiry_hooks

    monkeypatch.setattr(
        "app.platform.sales_qualify.bant_score",
        lambda rec: {"grade": "C", "total": 50, "action": ""},
    )
    monkeypatch.setattr("app.platform.lead_alerts.notify_new_lead_bg", lambda rec: None)
    monkeypatch.setattr("app.platform.team.log_event", lambda *a, **k: None)

    async def _fake_auto_callback(phone, niche, business, client_id=""):
        return None

    monkeypatch.setattr("app.api.public_site._auto_callback", _fake_auto_callback)
    asyncio.run(inquiry_hooks.run_after_inquiry(rec, **kw))


def test_lead_captured_logged_for_client_owned_inquiry(monkeypatch):
    logged = []
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.log_event",
        lambda cid, event, **k: logged.append((cid, event, k)),
    )
    rec = {
        "phone": "9998887777",
        "niche": "salon",
        "business_name": "Test Biz",
        "client_id": "client_abc",
    }
    _run_hook(rec, monkeypatch)

    matches = [e for e in logged if e[1] == "lead_captured"]
    assert len(matches) == 1
    assert matches[0][0] == "client_abc"
    assert matches[0][2]["detail"] == "Test Biz"


def test_lead_captured_not_logged_for_platform_lead(monkeypatch):
    """No client_id anywhere (platform's own /audit funnel) -> the `if cid:`
    block is skipped entirely, so the ledger must never be called."""
    logged = []
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.log_event",
        lambda cid, event, **k: logged.append((cid, event, k)),
    )
    rec = {"phone": "9998887777", "niche": "gym", "business_name": "No Client Lead"}
    _run_hook(rec, monkeypatch)

    assert logged == []


def test_lead_captured_ledger_failure_does_not_break_hook(monkeypatch):
    def _boom(cid, event, **k):
        raise RuntimeError("ledger down")

    monkeypatch.setattr("app.marketing.delivery_ledger.log_event", _boom)
    rec = {
        "phone": "9998887777",
        "niche": "salon",
        "business_name": "Test Biz",
        "client_id": "client_abc",
    }
    # Must not raise even though the ledger call inside run_after_inquiry blows up.
    _run_hook(rec, monkeypatch)


# ---------------------------------------------------------------------------
# followup_sent — app/api/public_site.py::_auto_callback
# ---------------------------------------------------------------------------
def _run_callback(monkeypatch, placed, client_id="client_xyz"):
    import app.api.public_site as ps

    async def _fake_start_stream_call(
        to,
        niche="general",
        client_id=None,
        call_type="transactional",
        opening_line="",
        dry_run=False,
    ):
        return {"placed": placed, "error": None if placed else "no answer"}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start_stream_call)
    monkeypatch.setattr("app.platform.team.log_event", lambda *a, **k: None)
    monkeypatch.setattr("app.platform.speed_to_lead.log_callback_touch", lambda *a, **k: None)

    logged = []
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.log_event",
        lambda cid, event, **k: logged.append((cid, event, k)),
    )
    asyncio.run(ps._auto_callback("9876543210", "salon", "Sharma Salon", client_id=client_id))
    return logged


def test_followup_sent_logged_when_callback_placed_for_client(monkeypatch):
    logged = _run_callback(monkeypatch, placed=True, client_id="client_xyz")
    matches = [e for e in logged if e[1] == "followup_sent"]
    assert len(matches) == 1
    assert matches[0][0] == "client_xyz"


def test_followup_sent_not_logged_when_callback_fails(monkeypatch):
    logged = _run_callback(monkeypatch, placed=False, client_id="client_xyz")
    assert logged == []


def test_followup_sent_not_logged_for_platform_lead(monkeypatch):
    """placed=True but client_id="" (platform-level /audit lead) -> no client
    to attribute the delivery event to, so it must not log."""
    logged = _run_callback(monkeypatch, placed=True, client_id="")
    assert logged == []


def test_followup_sent_ledger_failure_does_not_break_callback(monkeypatch):
    import app.api.public_site as ps

    async def _fake_start_stream_call(
        to,
        niche="general",
        client_id=None,
        call_type="transactional",
        opening_line="",
        dry_run=False,
    ):
        return {"placed": True}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start_stream_call)
    monkeypatch.setattr("app.platform.team.log_event", lambda *a, **k: None)
    monkeypatch.setattr("app.platform.speed_to_lead.log_callback_touch", lambda *a, **k: None)

    def _boom(cid, event, **k):
        raise RuntimeError("ledger down")

    monkeypatch.setattr("app.marketing.delivery_ledger.log_event", _boom)
    # Must not raise.
    asyncio.run(ps._auto_callback("9876543210", "salon", "Sharma Salon", client_id="client_xyz"))


# ---------------------------------------------------------------------------
# weekly_report_generated — app/marketing/client_report.py::build_report
# ---------------------------------------------------------------------------
def test_weekly_report_generated_logged_on_success(tmp_path, monkeypatch):
    from app.marketing import client_report as cr

    monkeypatch.setattr(cr, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: {"id": cid, "business_name": "Test Biz", "slug": "test-biz", "brand": {}},
    )

    logged = []
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.log_event",
        lambda cid, event, **k: logged.append((cid, event, k)),
    )

    result = asyncio.run(cr.build_report("client_abc", month="2026-07"))
    assert result["ok"] is True

    matches = [e for e in logged if e[1] == "weekly_report_generated"]
    assert len(matches) == 1
    assert matches[0][0] == "client_abc"
    assert matches[0][2]["detail"] == "2026-07"


def test_weekly_report_generated_not_logged_when_client_not_found(tmp_path, monkeypatch):
    from app.marketing import client_report as cr

    monkeypatch.setattr(cr, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: None)

    logged = []
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.log_event",
        lambda cid, event, **k: logged.append((cid, event, k)),
    )

    result = asyncio.run(cr.build_report("no_such_client", month="2026-07"))
    assert result["ok"] is False
    assert logged == []


def test_weekly_report_generated_ledger_failure_does_not_break_report(tmp_path, monkeypatch):
    from app.marketing import client_report as cr

    monkeypatch.setattr(cr, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: {"id": cid, "business_name": "Test Biz", "slug": "test-biz", "brand": {}},
    )

    def _boom(cid, event, **k):
        raise RuntimeError("ledger down")

    monkeypatch.setattr("app.marketing.delivery_ledger.log_event", _boom)

    result = asyncio.run(cr.build_report("client_abc", month="2026-07"))
    assert result["ok"] is True
