"""Contract tests — ledger-backed daily Product-1 paid activations (IST).

Product-1 ka north-star KPI (`docs/gtm/PRODUCT1_50_PAID_DAY_90D.md`) ab admin ke
"Aaj" snapshot pe number banta hai, isliye uski definition test me LOCK hai:
non-void marketing invoice YA approved/auto_activated UPI row, IST din pe, client
+ din pe dedupe, voided/voice/trial bahar.

Har test apni precondition khud set karta hai (R4): dono ledgers monkeypatch se
inject hote hain aur `day=` explicitly pass hota hai — koi wall-clock ya real
`data/` file pe depend nahi karta.
"""

from __future__ import annotations

import pytest

from app.billing import paid_activations as pa


@pytest.fixture
def ledgers(monkeypatch):
    """Inject both ledgers; returns a setter (invoices, upi)."""
    from app.billing import gst_invoice
    from app.platform import upi_payments

    def _set(invoices=None, upi=None):
        monkeypatch.setattr(gst_invoice, "list_invoices", lambda limit=50: list(invoices or []))
        monkeypatch.setattr(upi_payments, "list_payments", lambda status=None: list(upi or []))

    _set()
    return _set


def _invoice(client_id, created_at, plan="starter", gross=1999, **extra):
    return {
        "number": f"INV/2026-27/{abs(hash((client_id, created_at))) % 9999:04d}",
        "client_id": client_id,
        "plan": plan,
        "created_at": created_at,
        "gross_inr": gross,
        **extra,
    }


def _upi(client_id, decided_at, plan="starter", status="approved", **extra):
    return {
        "id": f"upi_{client_id}",
        "client_id": client_id,
        "plan": plan,
        "status": status,
        "decided_at": decided_at,
        **extra,
    }


# --------------------------- plan-key truth --------------------------- #
def test_marketing_plan_keys_from_packages_only():
    keys = pa.marketing_plan_keys()
    assert "starter" in keys, "Main ₹1,999 Marketing plan KPI me hona chahiye"
    assert "trial" not in keys, "FREE trial paid activation nahi hai"
    from app.marketing.combo_packages import COMBO_PLAN_IDS
    from app.marketing.voice_packages import VOICE_PLAN_IDS

    assert not (keys & {str(k).lower() for k in VOICE_PLAN_IDS})
    assert not (keys & {str(k).lower() for k in COMBO_PLAN_IDS})


def test_marketing_plan_keys_fail_closed_when_packages_unreadable(monkeypatch):
    """Pricing source na padhe to 0 report karo — guessed paid count kabhi nahi."""
    import app.marketing.packages as packages

    monkeypatch.delattr(packages, "PACKAGES")
    assert pa.marketing_plan_keys() == set()


# --------------------------- IST day boundary --------------------------- #
def test_ist_day_boundary_is_utc_plus_530():
    assert pa._ist_day("2026-08-15T18:29:00+00:00") == "2026-08-15"
    assert pa._ist_day("2026-08-15T18:30:00+00:00") == "2026-08-16"
    # naive ledger timestamp = UTC (ledgers UTC me likhte hain)
    assert pa._ist_day("2026-08-15T19:00:00") == "2026-08-16"
    assert pa._ist_day("") == ""
    assert pa._ist_day("not-a-date") == ""


def test_late_night_utc_invoice_lands_on_next_ist_day(ledgers):
    ledgers(invoices=[_invoice("c_late", "2026-08-15T19:00:00+00:00")])
    assert pa.daily_paid_activations("2026-08-15")["paid_today"] == 0
    assert pa.daily_paid_activations("2026-08-16")["activations_today"] == 1


# --------------------------- counting rules --------------------------- #
def test_invoice_today_is_a_new_paid_activation(ledgers):
    ledgers(invoices=[_invoice("jiya-makeover", "2026-08-15T06:00:00+00:00")])
    out = pa.daily_paid_activations("2026-08-15")
    assert out["paid_today"] == 1
    assert out["activations_today"] == 1
    assert out["gross_inr_today"] == 1999.0
    assert out["clients"][0]["client_id"] == "jiya-makeover"
    assert out["clients"][0]["sources"] == ["invoice"]


def test_voided_invoice_never_counts(ledgers):
    ledgers(invoices=[_invoice("c_void", "2026-08-15T06:00:00+00:00", voided=True)])
    out = pa.daily_paid_activations("2026-08-15")
    assert out["paid_today"] == 0 and out["gross_inr_today"] == 0.0


def test_voice_and_trial_plans_excluded(ledgers):
    from app.marketing.voice_packages import VOICE_PLAN_IDS

    ledgers(
        invoices=[
            _invoice("c_voice", "2026-08-15T06:00:00+00:00", plan=VOICE_PLAN_IDS[0], gross=4999),
            _invoice("c_trial", "2026-08-15T06:00:00+00:00", plan="trial", gross=0),
        ]
    )
    assert pa.daily_paid_activations("2026-08-15")["paid_today"] == 0


def test_upi_approved_counts_and_rejected_does_not(ledgers):
    ledgers(
        upi=[
            _upi("c_ok", "2026-08-15T07:00:00+00:00", status="approved"),
            _upi("c_auto", "2026-08-15T07:00:00+00:00", status="auto_activated"),
            # activated=True leftover on a later-rejected row must NOT count
            _upi("c_bad", "2026-08-15T07:00:00+00:00", status="rejected", activated=True),
        ]
    )
    out = pa.daily_paid_activations("2026-08-15")
    assert out["paid_today"] == 2
    assert {c["client_id"] for c in out["clients"]} == {"c_ok", "c_auto"}


def test_pending_upi_is_not_paid(ledgers):
    ledgers(upi=[_upi("c_pending", "2026-08-15T07:00:00+00:00", status="pending")])
    assert pa.daily_paid_activations("2026-08-15")["paid_today"] == 0


def test_same_client_invoice_plus_upi_dedupes_to_one(ledgers):
    """UPI approve khud ek GST invoice fire karta hai — bina dedupe ke 1 customer 2 ginta."""
    ledgers(
        invoices=[_invoice("c_dup", "2026-08-15T07:05:00+00:00")],
        upi=[_upi("c_dup", "2026-08-15T07:00:00+00:00")],
    )
    out = pa.daily_paid_activations("2026-08-15")
    assert out["paid_today"] == 1 and out["activations_today"] == 1
    assert sorted(out["clients"][0]["sources"]) == ["invoice", "upi"]
    assert out["events_by_source"] == {"invoice": 1, "upi": 1}


def test_renewal_is_paid_today_but_not_a_new_activation(ledgers):
    ledgers(
        invoices=[
            _invoice("c_old", "2026-07-15T06:00:00+00:00"),
            _invoice("c_old", "2026-08-15T06:00:00+00:00"),
            _invoice("c_new", "2026-08-15T06:00:00+00:00"),
        ]
    )
    out = pa.daily_paid_activations("2026-08-15")
    assert out["paid_today"] == 2, "renewal bhi paid event hai"
    assert out["activations_today"] == 1, "sirf pehli baar paid = new activation"
    assert {c["client_id"]: c["new"] for c in out["clients"]} == {"c_new": True, "c_old": False}


def test_unbound_upi_row_without_client_is_skipped(ledgers):
    ledgers(upi=[_upi("", "2026-08-15T07:00:00+00:00")])
    assert pa.daily_paid_activations("2026-08-15")["paid_today"] == 0


# --------------------------- never-raise posture --------------------------- #
def test_broken_ledgers_report_zero_not_an_error(monkeypatch):
    from app.billing import gst_invoice
    from app.platform import upi_payments

    def _boom(*_a, **_kw):
        raise RuntimeError("store down")

    monkeypatch.setattr(gst_invoice, "list_invoices", _boom)
    monkeypatch.setattr(upi_payments, "list_payments", _boom)
    out = pa.daily_paid_activations("2026-08-15")
    assert out["paid_today"] == 0 and out["activations_today"] == 0
    assert out["day"] == "2026-08-15" and out["tz"] == "Asia/Kolkata"


# --------------------------- admin "Aaj" wiring --------------------------- #
def test_today_overview_exposes_paid_activation_totals(monkeypatch):
    from app.platform import today_overview

    monkeypatch.setattr(
        pa,
        "daily_paid_activations",
        lambda *a, **k: {"paid_today": 3, "activations_today": 2, "gross_inr_today": 5997.0},
    )
    totals = today_overview.build()["totals"]
    assert totals["paid_today"] == 3
    assert totals["activations_today"] == 2
    assert totals["paid_gross_today_inr"] == 5997.0


def test_today_overview_paid_totals_fail_open_zero(monkeypatch):
    from app.platform import today_overview

    def _boom(*_a, **_kw):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(pa, "daily_paid_activations", _boom)
    totals = today_overview.build()["totals"]
    assert totals["paid_today"] == 0 and totals["activations_today"] == 0
