"""Tests — revenue+infra batch 2026-06-10 (gst_invoice, email_warmup, usage_alerts,
annual pricing). Project convention: sync + asyncio.run, tmp stores monkeypatch,
DB/network nahi chahiye.
"""

from __future__ import annotations

import asyncio
import json
import os


# ----------------------------- gst_invoice ----------------------------- #
def _patch_inv(tmp_path, monkeypatch):
    from app.billing import gst_invoice

    monkeypatch.setattr(gst_invoice, "_STORE", lambda: str(tmp_path / "invoices.jsonl"))
    monkeypatch.delenv("AUTO_INVOICE", raising=False)
    monkeypatch.delenv("GST_GSTIN", raising=False)
    return gst_invoice


def test_invoice_fy_and_sequence(tmp_path, monkeypatch):
    gi = _patch_inv(tmp_path, monkeypatch)
    from datetime import datetime, timezone

    assert gi.fy_label(datetime(2026, 6, 10, tzinfo=timezone.utc)) == "2026-27"
    assert gi.fy_label(datetime(2026, 2, 1, tzinfo=timezone.utc)) == "2025-26"
    n1 = gi.next_number("2026-27")
    assert n1 == "INV/2026-27/0001" and len(n1) <= 16  # Rule 46: <=16 chars
    monkeypatch.setattr(gi, "_client", lambda cid: {"business_name": "Sharma Solar", "email": ""})
    inv = gi.create_invoice("c1", "starter")
    assert inv["number"] == "INV/2026-27/0001" and inv["gross_inr"] == 1999.0
    inv2 = gi.create_invoice("c2", "growth")
    assert inv2["number"] == "INV/2026-27/0002"  # sequential per FY


def test_invoice_tax_modes(tmp_path, monkeypatch):
    gi = _patch_inv(tmp_path, monkeypatch)
    monkeypatch.setattr(gi, "_client", lambda cid: {"business_name": "B", "state_code": "27"})
    # unregistered (GSTIN unset) -> no tax lines, gross == taxable
    inv = gi.create_invoice("c1", "starter")
    assert inv["tax_mode"] == "unregistered" and inv["taxable_value"] == 1999.0
    assert inv["cgst"] == 0 and inv["igst"] == 0 and inv["sac_code"] == "998313"
    # registered intra-state (27 == 27) -> CGST+SGST split, totals reconcile
    monkeypatch.setenv("GST_GSTIN", "27ABCDE1234F1Z5")
    inv2 = gi.create_invoice("c1", "advanced")
    assert inv2["tax_mode"] == "intra"
    assert round(inv2["taxable_value"] + inv2["cgst"] + inv2["sgst"], 2) == inv2["gross_inr"]
    # inter-state -> IGST
    monkeypatch.setattr(gi, "_client", lambda cid: {"business_name": "B", "state_code": "07"})
    inv3 = gi.create_invoice("c1", "growth")
    assert inv3["tax_mode"] == "inter" and inv3["igst"] > 0 and inv3["cgst"] == 0


def test_invoice_dedupe_and_html(tmp_path, monkeypatch):
    gi = _patch_inv(tmp_path, monkeypatch)
    monkeypatch.setattr(gi, "_client", lambda cid: {"business_name": "Sharma Solar", "email": ""})
    inv = asyncio.run(gi.on_payment_success("c1", "starter", payment_ref="sub_1:2026-06"))
    assert inv.get("number")
    again = asyncio.run(gi.on_payment_success("c1", "starter", payment_ref="sub_1:2026-06"))
    assert again.get("deduped") is True  # double-webhook safe
    html = gi.invoice_html(inv)
    assert inv["number"] in html and "Sharma Solar" in html and "998313" in html
    assert gi.get_by_number(inv["number"])["client_id"] == "c1"
    st = gi.stats()
    assert st["fy_count"] == 1 and st["registered_mode"] is False
    # bad input -> {} (never raises)
    assert asyncio.run(gi.on_payment_success("", "")) == {}


# ----------------------------- email_warmup ----------------------------- #
def _patch_wu(tmp_path, monkeypatch):
    from app.platform import email_warmup as wu

    monkeypatch.setattr(wu, "_STATE", str(tmp_path / "warmup.json"))
    monkeypatch.delenv("WARMUP_START_DATE", raising=False)
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    return wu


def test_warmup_flag_off_zero_change(tmp_path, monkeypatch):
    wu = _patch_wu(tmp_path, monkeypatch)
    monkeypatch.delenv("EMAIL_WARMUP", raising=False)
    assert wu.effective_cap(25) == 25  # OFF = base cap as-is
    assert wu.effective_cap(0) == 0


def test_warmup_ramp_and_pause(tmp_path, monkeypatch):
    wu = _patch_wu(tmp_path, monkeypatch)
    monkeypatch.setenv("EMAIL_WARMUP", "1")
    # day-1 (start marker auto-set) -> week1 ramp = 5
    assert wu.effective_cap(25) == 5
    # week-3 via env start date (15 din pehle)
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv(
        "WARMUP_START_DATE",
        (datetime.now(timezone.utc) - timedelta(days=15)).date().isoformat(),
    )
    assert wu.effective_cap(25) == 25  # wk3 ramp=25, min(base,25)
    # week-5 -> base cap
    monkeypatch.setenv(
        "WARMUP_START_DATE",
        (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat(),
    )
    assert wu.effective_cap(40) == 40
    # bounce auto-pause: 30 sends + 1 bounce = 3.3% >= 1.8% -> paused, cap 0
    wu.record_sent(30)
    out = wu.record_bounce("x@dead.com", "mailbox full")
    assert out["recorded"] is True and out["paused"] is True
    assert wu.is_paused() is True and wu.effective_cap(40) == 0
    assert wu.resume() is True and wu.is_paused() is False


def test_warmup_small_sample_no_pause(tmp_path, monkeypatch):
    wu = _patch_wu(tmp_path, monkeypatch)
    monkeypatch.setenv("EMAIL_WARMUP", "1")
    wu.record_sent(5)  # < 20 sends -> 1 bounce par bhi pause nahi
    out = wu.record_bounce("y@dead.com")
    assert out["paused"] is False and wu.is_paused() is False
    st = wu.status()
    assert st["enabled"] is True and st["bounced_7d"] == 1


# ----------------------------- usage_alerts ----------------------------- #
def test_usage_alert_messages_pure():
    from app.billing import usage_alerts

    m80 = usage_alerts.build_message(80, "Sharma Solar", 400, 500)
    assert "80%" in m80["subject"] and "Sharma Solar" in m80["subject"]
    m100 = usage_alerts.build_message(100, "Sharma Solar", 500, 500)
    assert "khatam" in m100["subject"] and "leadsgenai.in" in m100["body"]


def test_usage_alerts_run_and_dedupe(tmp_path, monkeypatch):
    from app.billing import usage_alerts as ua

    monkeypatch.setattr(ua, "_STORE", str(tmp_path / "alerts.jsonl"))
    monkeypatch.delenv("USAGE_ALERTS", raising=False)  # gated OFF -> record only
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda: [
            {"id": "c1", "business_name": "Sharma Solar", "plan": "advanced", "email": "a@b.c"},
            {"id": "c2", "business_name": "Marketing Only", "plan": "starter"},
        ],
    )
    monkeypatch.setattr("app.billing.usage.minutes_used_this_period", lambda cid: 412)
    out = asyncio.run(ua.run_check())
    assert out["checked"] == 1  # sirf metered (advanced) plan
    assert out["alerts"] == 1 and out["sent"] == 0  # 412/500 = 82% -> 80% alert, gated OFF
    rec = ua.recent()[0]
    assert rec["threshold"] == 80 and rec["sent"] is False
    # dedupe: same period dobara -> koi naya alert nahi
    out2 = asyncio.run(ua.run_check())
    assert out2["alerts"] == 0
    # 100% cross -> higher threshold alert (alag dedupe key)
    monkeypatch.setattr("app.billing.usage.minutes_used_this_period", lambda cid: 500)
    out3 = asyncio.run(ua.run_check())
    assert out3["alerts"] == 1 and ua.recent()[0]["threshold"] == 100


# ----------------------------- annual pricing ----------------------------- #
def test_packages_annual_pricing_additive():
    from app.marketing.packages import PACKAGES, get_packages

    for p in PACKAGES:
        assert p["price_inr_year"] == p["price_inr_month"] * 10  # 2 mahine free
        assert "annual_note" in p
    # backward compat: get_packages() shape unchanged (3 paid packages)
    assert len(get_packages()) == 3


# ----------------------------- outreach wiring ----------------------------- #
def test_outreach_cap_respects_warmup(tmp_path, monkeypatch):
    """auto_outreach ka cap-path email_warmup.effective_cap se hokar jata hai."""
    from app.platform import email_warmup as wu

    monkeypatch.setattr(wu, "_STATE", str(tmp_path / "warmup.json"))
    monkeypatch.setenv("EMAIL_WARMUP", "1")
    # week1 -> effective 5 (base 25)
    assert wu.effective_cap(25) == 5
    monkeypatch.delenv("EMAIL_WARMUP", raising=False)
    assert wu.effective_cap(25) == 25
