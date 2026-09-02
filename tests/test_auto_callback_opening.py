"""Tests: audit auto-callback greeting wizard opening_line use karta hai.

- _wizard_opening_for(rec) — inquiry business_type/niche se wizard preview resolve.
- _answer_stream_qs + start_stream_call opening_line ko pending + qs tak pahunchate hain.
- _auto_callback opening_line ko start_stream_call ko pass karta hai.
- VobizStreamSession(opening_line=...) greeting me override set karta hai (aur
  compliance wrap — AI disclosure + permission ask — abhi bhi active rehta hai).
"""

from __future__ import annotations

import pytest

from app.platform import inquiry_hooks as hooks


def test_wizard_opening_resolves_from_business_type_label():
    rec = {
        "business_type": "Salon / Beauty Parlour",
        "niche": "salon_spa",
        "business_name": "Sharma Salon",
    }
    out = hooks._wizard_opening_for(rec)
    assert "Sharma Salon" in out
    assert "Swara" in out
    assert out.startswith("Namaste")


def test_wizard_opening_resolves_from_niche_key():
    rec = {"business_type": "", "niche": "salon_spa", "business_name": "Sharma Salon"}
    out = hooks._wizard_opening_for(rec)
    assert "Sharma Salon" in out


def test_wizard_opening_empty_for_unknown():
    assert (
        hooks._wizard_opening_for(
            {"business_type": "Kuch Bhi", "niche": "nope", "business_name": "X"}
        )
        == ""
    )
    assert hooks._wizard_opening_for({"business_type": "", "niche": "", "business_name": "X"}) == ""
    assert (
        hooks._wizard_opening_for(
            {"business_type": "Salon", "niche": "salon_spa", "business_name": ""}
        )
        == ""
    )


def test_answer_stream_qs_includes_opening_line():
    import app.api.telephony_vobiz as tv

    qs = tv._answer_stream_qs(
        "salon_spa",
        None,
        lead_phone="9876543210",
        opening_line="Namaste, main Swara bol rahi hoon Sharma Salon ki taraf se.",
    )
    assert "opening_line=" in qs
    assert "Sharma+Salon" in qs


def test_start_stream_call_stores_opening_line_in_pending(monkeypatch):
    import app.api.telephony_vobiz as tv

    pending: dict = {}

    class _FakeVobiz:
        def available(self):
            return True

        async def place_call(self, **kw):
            return {"status_code": 200}

    async def _fake_store(token, data):
        pending.update({token: data})

    monkeypatch.setattr(tv, "VobizClient", _FakeVobiz)
    monkeypatch.setattr(tv, "_store_pending", _fake_store)
    monkeypatch.setattr(tv, "_sign_stream_token", lambda x: "tok123")
    monkeypatch.setattr(tv, "settings", type("S", (), {"public_base_url": "https://x.in"})())

    import asyncio

    res = asyncio.run(
        tv.start_stream_call(
            "9876543210",
            niche="salon_spa",
            opening_line="Namaste, main Swara bol rahi hoon Sharma Salon ki taraf se.",
        )
    )
    assert res.get("placed") is True
    rec = next(iter(pending.values()))
    assert "Sharma Salon" in rec["opening_line"]
    assert "opening_line=" in res["answer_url"]


def test_auto_callback_passes_opening_line(monkeypatch):
    import app.api.telephony_vobiz as tv

    seen: dict = {}

    async def _fake_start_stream_call(**kw):
        seen.update(kw)
        return {"placed": False, "error": "noop"}

    monkeypatch.setattr(tv, "start_stream_call", _fake_start_stream_call)

    import asyncio

    import app.api.public_site as ps

    asyncio.run(
        ps._auto_callback(
            "9876543210", "salon_spa", "Sharma Salon", opening_line="Wizard wali opening"
        )
    )
    assert seen.get("opening_line") == "Wizard wali opening"


def test_session_opening_override_used_and_compliance_wrapped():
    """Caller opening_line greeting pe override hota hai + AI disclosure + permission
    ask abhi bhi active (compliance spine untouched)."""
    from app.telephony.vobiz_stream import VobizStreamSession

    s = VobizStreamSession(
        websocket=None,
        niche="salon_spa",
        client_name="LeadGen AI",
        opening_line="Namaste, main Swara bol rahi hoon Sharma Salon ki taraf se.",
    )
    assert (
        s._flywheel_opening_override
        == "Namaste, main Swara bol rahi hoon Sharma Salon ki taraf se."
    )
    line = s._opening_line()
    low = line.lower()
    assert "ai" in low and ("assistant" in low or "swara" in low)  # disclosure present
    assert "?" in line  # permission/timing ask present


def test_session_opening_default_is_none():
    from app.telephony.vobiz_stream import VobizStreamSession

    s = VobizStreamSession(websocket=None, niche="salon_spa")
    assert s._flywheel_opening_override is None


def test_resolve_wizard_opening_scalar_api():
    """Reusable scalar resolver (shared by auto-callback / followup / missed-call)."""
    out = hooks.resolve_wizard_opening(
        business_type="Salon / Beauty Parlour", niche="salon_spa", business_name="Sharma Salon"
    )
    assert "Sharma Salon" in out and "Swara" in out
    # niche-key alone bhi match karta hai
    assert "Sharma Salon" in hooks.resolve_wizard_opening(
        niche="salon_spa", business_name="Sharma Salon"
    )
    # business_name zaroori hai; unknown niche/type → ""
    assert hooks.resolve_wizard_opening(niche="salon_spa", business_name="") == ""
    assert hooks.resolve_wizard_opening(niche="nope", business_name="X") == ""
    assert hooks.resolve_wizard_opening(business_type="Kuch Bhi", business_name="X") == ""
    assert hooks.resolve_wizard_opening(business_name="X") == ""


@pytest.mark.asyncio
async def test_missed_call_passes_wizard_opening(monkeypatch):
    """Missed-call callback start_stream_call ko wizard opening_line de."""
    import app.telephony.missed_call as mc

    seen: dict = {}

    async def _fake_start(to, **kw):
        seen.update({"to": to, **kw})
        return {"placed": True}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start)
    monkeypatch.setattr("app.api.public_site._append_jsonl", lambda *a, **k: None)
    monkeypatch.setattr("app.api.public_site._save_lead_db", lambda *a, **k: None)
    monkeypatch.setenv("MISSED_CALL_CALLBACK", "1")

    out = await mc.handle_missed_call("919876543210", niche="salon_spa", business="Sharma Salon")
    assert out.get("callback") is True
    assert "Sharma Salon" in seen.get("opening_line", "")
    assert seen.get("niche") == "salon_spa"


@pytest.mark.asyncio
async def test_missed_call_falls_back_empty_opening(monkeypatch):
    """Bina wizard-context missed call → opening_line "" (niche-script chain intact)."""
    import app.telephony.missed_call as mc

    seen: dict = {}

    async def _fake_start(to, **kw):
        seen.update({"to": to, **kw})
        return {"placed": True}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start)
    monkeypatch.setattr("app.api.public_site._append_jsonl", lambda *a, **k: None)
    monkeypatch.setattr("app.api.public_site._save_lead_db", lambda *a, **k: None)
    monkeypatch.setenv("MISSED_CALL_CALLBACK", "1")

    await mc.handle_missed_call("919876543211", niche="general", business="")
    assert seen.get("opening_line") == ""


def test_start_stream_call_dry_run_skips_dial(monkeypatch):
    """dry_run=True → pending + answer_url poora banta hai, par place_call kabhi nahi."""
    import app.api.telephony_vobiz as tv

    pending: dict = {}
    dialed: list = []

    class _FakeVobiz:
        def available(self):
            return True

        async def place_call(self, **kw):
            dialed.append(kw)
            return {"status_code": 200}

    async def _fake_store(token, data):
        pending.update({token: data})

    monkeypatch.setattr(tv, "VobizClient", _FakeVobiz)
    monkeypatch.setattr(tv, "_store_pending", _fake_store)
    monkeypatch.setattr(tv, "_sign_stream_token", lambda x: "tokdry")
    monkeypatch.setattr(tv, "settings", type("S", (), {"public_base_url": "https://x.in"})())

    import asyncio

    res = asyncio.run(
        tv.start_stream_call(
            "9876543210", niche="salon_spa", opening_line="Wizard wali opening", dry_run=True
        )
    )
    assert res.get("placed") is True
    assert res.get("dry_run") is True
    assert not dialed  # NO real dial
    rec = next(iter(pending.values()))
    assert rec["opening_line"] == "Wizard wali opening"
    assert "opening_line=" in res["answer_url"]


def test_auto_callback_dry_run_skips_business_ledgers(monkeypatch):
    """dry_run auto-callback: placed-report aata hai par speed_to_lead/delivery
    ledgers untouched (no real call = no business side-effects)."""
    import app.api.public_site as ps

    touches: list = []
    ledger: list = []

    async def _fake_start(**kw):
        return {"placed": True, "dry_run": True, "stream_token": "tokx"}

    import app.api.telephony_vobiz as tv

    monkeypatch.setattr(tv, "start_stream_call", _fake_start)
    monkeypatch.setattr(
        "app.platform.speed_to_lead.log_callback_touch", lambda *a, **k: touches.append(a)
    )
    monkeypatch.setattr("app.marketing.delivery_ledger.log_event", lambda *a, **k: ledger.append(a))
    monkeypatch.setattr("app.platform.team.log_event", lambda *a, **k: None)

    import asyncio

    asyncio.run(
        ps._auto_callback(
            "9876543210",
            "salon_spa",
            "Sharma Salon",
            client_id="c1",
            opening_line="W",
            dry_run=True,
        )
    )
    assert not touches and not ledger

    # default (dry_run=False) → real side-effects waapas
    asyncio.run(
        ps._auto_callback(
            "9876543210", "salon_spa", "Sharma Salon", client_id="c1", opening_line="W"
        )
    )
    assert len(touches) == 1
    assert len(ledger) == 1


def test_run_after_inquiry_threads_dry_run(monkeypatch):
    """run_after_inquiry(dry_run=True) → _auto_callback(dry_run=True)."""
    import app.platform.inquiry_hooks as hooks

    seen: dict = {}

    async def _fake_auto_callback(
        phone, niche, business, client_id="", opening_line="", dry_run=False
    ):
        seen.update(phone=phone, dry_run=dry_run)

    monkeypatch.setattr("app.api.public_site._auto_callback", _fake_auto_callback)
    monkeypatch.setattr(
        "app.platform.sales_qualify.bant_score",
        lambda rec: {"grade": "C", "total": 50, "action": ""},
    )
    monkeypatch.setattr("app.platform.lead_alerts.notify_new_lead_bg", lambda rec: None)
    monkeypatch.setattr("app.platform.team.log_event", lambda *a, **k: None)

    import asyncio

    asyncio.run(
        hooks.run_after_inquiry(
            {"phone": "9998887777", "niche": "salon_spa", "business_name": "Sharma Salon"},
            dry_run=True,
        )
    )
    assert seen.get("dry_run") is True

    seen.clear()
    asyncio.run(
        hooks.run_after_inquiry(
            {"phone": "9998887777", "niche": "salon_spa", "business_name": "Sharma Salon"}
        )
    )
    assert seen.get("dry_run") is False
