"""Self-serve UPI payments — submit queue, list filter, approve/reject, auto-activate.

Pure python: store path monkeypatched to tmp_path, no network/DB.
``usage.activate_plan`` is stubbed where activation behaviour is asserted.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def up(tmp_path, monkeypatch):
    """upi_payments module with its store pointed at a tmp file."""
    from app.platform import upi_payments as mod

    monkeypatch.setattr(mod, "_STORE", str(tmp_path / "upi_payments.json"))
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)
    return mod


def test_submit_creates_pending(up):
    out = up.submit_payment("cli_1", "growth", "TXN123", amount=2999, payer_name="Sumit")
    assert out["ok"] is True
    assert out["status"] == "pending"
    assert out["auto_activated"] is False
    assert out["client_id"] == "cli_1"
    assert out["plan"] == "growth"
    assert out["upi_ref"] == "TXN123"
    assert out["id"].startswith("upi_1_")
    # persisted as pending
    pend = up.list_payments("pending")
    assert len(pend) == 1
    assert pend[0]["id"] == out["id"]


def test_submit_validates_plan_and_ref(up):
    assert up.submit_payment("cli_1", "", "TXN1")["ok"] is False
    assert up.submit_payment("cli_1", "growth", "")["ok"] is False
    assert up.list_payments() == []


def test_list_payments_filters_by_status(up):
    up.submit_payment("cli_1", "starter", "T1")
    up.submit_payment("cli_2", "growth", "T2")
    all_rows = up.list_payments()
    assert len(all_rows) == 2
    # reject one → it leaves the pending filter
    rid = all_rows[0]["id"]
    up.decide(rid, False)
    pend = up.list_payments("pending")
    assert len(pend) == 1
    rej = up.list_payments("rejected")
    assert len(rej) == 1
    assert rej[0]["id"] == rid


def test_decide_approve_flips_to_approved(up, monkeypatch):
    from app.billing import usage

    calls: list[tuple] = []
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: calls.append((cid, plan)) or True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    sub = up.submit_payment("cli_9", "advanced", "TXN999")
    rec = up.decide(sub["id"], True, decided_by="boss")
    assert rec["status"] == "approved"
    assert rec["decided_by"] == "boss"
    assert rec["decided_at"] is not None
    # approve with client_id → activate_plan invoked
    assert calls == [("cli_9", "advanced")]


def test_decide_reject(up):
    sub = up.submit_payment("cli_5", "starter", "TXN5")
    rec = up.decide(sub["id"], False)
    assert rec["status"] == "rejected"


def test_decide_not_found(up):
    out = up.decide("nope", True)
    assert out["ok"] is False
    assert out["error"] == "not_found"


def test_auto_activate_flag(up, monkeypatch):
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    out = up.submit_payment("cli_auto", "growth", "TXNAUTO")
    assert out["ok"] is True
    assert out["status"] == "auto_activated"
    assert out["auto_activated"] is True
    # persisted with auto_activated status (not pending)
    assert up.list_payments("pending") == []
    assert len(up.list_payments("auto_activated")) == 1


def test_auto_activate_skipped_without_client(up, monkeypatch):
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)

    # no client_id → cannot auto-activate, stays pending
    out = up.submit_payment("", "growth", "TXNNOCID")
    assert out["status"] == "pending"
    assert out["auto_activated"] is False


def test_decide_approve_triggers_onboarding(up, monkeypatch):
    """Admin approve → plan activates → onboarding is front-run (no <=1h wait)."""
    monkeypatch.setattr(up, "_try_activate", lambda cid, plan: True)
    fired: list[int] = []
    monkeypatch.setattr(up, "_trigger_onboarding", lambda: fired.append(1))

    sub = up.submit_payment("cli_ob", "advanced", "TXNOB")
    up.decide(sub["id"], True)
    assert fired == [1]


def test_decide_reject_no_onboarding(up, monkeypatch):
    """Reject must NOT trigger onboarding."""
    monkeypatch.setattr(up, "_try_activate", lambda cid, plan: True)
    fired: list[int] = []
    monkeypatch.setattr(up, "_trigger_onboarding", lambda: fired.append(1))

    sub = up.submit_payment("cli_rej", "starter", "TXNREJ")
    up.decide(sub["id"], False)
    assert fired == []


def test_auto_activate_triggers_onboarding(up, monkeypatch):
    """Instant auto-activate path also front-runs onboarding."""
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)
    fired: list[int] = []
    monkeypatch.setattr(up, "_trigger_onboarding", lambda: fired.append(1))

    out = up.submit_payment("cli_auto_ob", "growth", "TXNAUTOOB")
    assert out["status"] == "auto_activated"
    assert fired == [1]


def test_trigger_onboarding_never_raises(up, monkeypatch):
    """Broker/enqueue failure must be swallowed (hourly sweep is the fallback)."""
    import app.worker as w

    def boom(*a, **k):
        raise RuntimeError("broker down")

    monkeypatch.setattr(w.celery_app, "send_task", boom)
    assert up._trigger_onboarding() is None


def test_decide_approve_invalid_plan_no_activation(up, monkeypatch):
    """An UNKNOWN/typo plan must be rejected BEFORE activate_plan is ever called —
    the plan does not provision and the record is not marked auto_activated."""
    from app.billing import usage

    calls: list[tuple] = []
    monkeypatch.setattr(
        usage, "activate_plan", lambda cid, plan, **kw: calls.append((cid, plan)) or True
    )

    sub = up.submit_payment("cli_bad", "bogus_plan_xyz", "TXNBAD")
    rec = up.decide(sub["id"], True, decided_by="boss")
    # plan rejected → activate_plan NEVER invoked
    assert calls == []
    # record not auto-activated by the rejected plan
    assert rec.get("auto_activated") is False


def test_decide_approve_resets_usage_period(up, monkeypatch):
    """A successful activation on a VALID plan also resets the metered-usage
    watermark (parity with the Stripe webhook path) — reset fires exactly once."""
    from app.billing import usage

    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    resets: list[str] = []
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: resets.append(cid) or True)

    sub = up.submit_payment("cli_reset", "advanced", "TXNRESET")
    up.decide(sub["id"], True, decided_by="boss")
    assert resets == ["cli_reset"]
