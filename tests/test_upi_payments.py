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

    monkeypatch.setattr(mod, "_STORE", lambda: str(tmp_path / "upi_payments.json"))
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)
    monkeypatch.delenv("UPI_AUTO_ACTIVATE_CLIENTS", raising=False)
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
    monkeypatch.setattr(
        usage, "activate_plan", lambda cid, plan, **kw: calls.append((cid, plan)) or True
    )
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    sub = up.submit_payment("cli_9", "advanced", "TXN999", amount=5999)
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
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    out = up.submit_payment("cli_auto", "growth", "TXNAUTO", amount=2999)
    assert out["ok"] is True
    assert out["status"] == "auto_activated"
    assert out["auto_activated"] is True
    # persisted with auto_activated status (not pending)
    assert up.list_payments("pending") == []
    assert len(up.list_payments("auto_activated")) == 1


def test_auto_activate_fail_closed_without_clients_allowlist(up, monkeypatch):
    """UPI_AUTO_ACTIVATE=1 with empty CLIENTS must NOT activate (fail-closed)."""
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.delenv("UPI_AUTO_ACTIVATE_CLIENTS", raising=False)
    called: list[str] = []
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: called.append(cid) or True)

    out = up.submit_payment("cli_blocked", "growth", "TXNNOALLOW", amount=2999)
    assert out["ok"] is True
    assert out["status"] == "pending"
    assert out["auto_activated"] is False
    assert called == []


def test_auto_activate_wrong_tenant_refused(up, monkeypatch):
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "allowed-client")
    called: list[str] = []
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: called.append(cid) or True)

    out = up.submit_payment("other-client", "growth", "TXNWRONG", amount=2999)
    assert out["status"] == "pending"
    assert out["auto_activated"] is False
    assert called == []

    out2 = up.submit_payment("allowed-client", "growth", "TXNOK", amount=2999)
    assert out2["status"] == "auto_activated"
    assert called == ["allowed-client"]


def test_auto_activate_skipped_without_client(up, monkeypatch):
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)

    # no client_id → cannot auto-activate, stays pending
    out = up.submit_payment("", "growth", "TXNNOCID")
    assert out["status"] == "pending"
    assert out["auto_activated"] is False


def test_decide_approve_triggers_onboarding(up, monkeypatch):
    """Admin approve → plan activates → onboarding is front-run (no <=1h wait)."""
    monkeypatch.setattr(up, "_try_activate", lambda cid, plan, amount=0, **kw: True)
    fired: list[int] = []
    monkeypatch.setattr(up, "_trigger_onboarding", lambda *_a, **_k: fired.append(1))

    sub = up.submit_payment("cli_ob", "advanced", "TXNOB")
    up.decide(sub["id"], True)
    assert fired == [1]


def test_decide_reject_no_onboarding(up, monkeypatch):
    """Reject must NOT trigger onboarding."""
    monkeypatch.setattr(up, "_try_activate", lambda cid, plan, amount=0, **kw: True)
    fired: list[int] = []
    monkeypatch.setattr(up, "_trigger_onboarding", lambda *_a, **_k: fired.append(1))

    sub = up.submit_payment("cli_rej", "starter", "TXNREJ")
    up.decide(sub["id"], False)
    assert fired == []


def test_auto_activate_triggers_onboarding(up, monkeypatch):
    """Instant auto-activate path also front-runs onboarding."""
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)
    fired: list[int] = []
    monkeypatch.setattr(up, "_trigger_onboarding", lambda *_a, **_k: fired.append(1))

    out = up.submit_payment("cli_auto_ob", "growth", "TXNAUTOOB", amount=2999)
    assert out["status"] == "auto_activated"
    assert fired == [1]


def test_auto_activate_nudges_founder_spot_check(up, monkeypatch):
    """Council decision 2026-07-03: instant activation on an unverified
    self-reported payment must fire the spot-check nudge (mitigates the
    fraud-risk dissent without reintroducing the manual-approve wait)."""
    from app.billing import usage
    from app.platform import ops_alerts

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)
    monkeypatch.setattr(up, "_mark_deal_won", lambda phone: None)

    nudged: list[tuple] = []
    monkeypatch.setattr(
        ops_alerts,
        "maybe_alert_upi_auto_activated",
        lambda pid, cid, plan, amount: nudged.append((pid, cid, plan, amount)),
    )

    out = up.submit_payment(
        "cli_nudge", "advanced", "TXNNUDGE", amount=5999, payer_contact="9999999999"
    )

    assert out["status"] == "auto_activated"
    assert len(nudged) == 1
    _pid, cid, plan, amount = nudged[0]
    assert cid == "cli_nudge"
    assert plan == "advanced"
    assert amount == 5999


def test_auto_activate_nudge_never_raises(up, monkeypatch):
    """A broken/misconfigured ntfy must never undo an already-successful
    activation — the customer's plan stays active even if the nudge fails."""
    from app.billing import usage
    from app.platform import ops_alerts

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    def _boom(*a, **k):
        raise RuntimeError("ntfy unreachable")

    monkeypatch.setattr(ops_alerts, "maybe_alert_upi_auto_activated", _boom)

    out = up.submit_payment("cli_nudge_fail", "advanced", "TXNNUDGEFAIL", amount=5999)
    assert out["status"] == "auto_activated"


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

    sub = up.submit_payment("cli_reset", "advanced", "TXNRESET", amount=5999)
    up.decide(sub["id"], True, decided_by="boss")
    assert resets == ["cli_reset"]


def test_auto_activate_rejects_fabricated_low_amount(up, monkeypatch):
    """Production audit 2026-07-01: UPI_AUTO_ACTIVATE only checked the plan key,
    not the paid amount — a self-serve submission claiming amount:0 (or any
    amount below the plan's real price) could auto-activate a paid plan for
    free. Must stay pending, not silently provision."""
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    calls: list[tuple] = []
    monkeypatch.setattr(
        usage, "activate_plan", lambda cid, plan, **kw: calls.append((cid, plan)) or True
    )

    # advanced plan costs ₹5999 — submitting ₹0 must NOT activate it.
    out = up.submit_payment("cli_cheap", "advanced", "TXNCHEAP", amount=0)
    assert out["status"] == "pending"
    assert out["auto_activated"] is False
    assert calls == [], "activate_plan must NEVER be called for a below-price amount"


def test_auto_activate_accepts_real_amount(up, monkeypatch):
    """Sanity check: the fix doesn't break the legitimate case — a real,
    at-or-above-price amount still auto-activates."""
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    out = up.submit_payment("cli_real", "advanced", "TXNREAL", amount=5999)
    assert out["status"] == "auto_activated"


def test_decide_approve_activates_amount_zero_submission(up, monkeypatch):
    """P0 audit 2026-07-04: every frontend submit records amount=0 (no amount
    field in the UPI modals), and decide() re-ran the price floor against that
    recorded amount — so the admin Approve button NEVER activated a real-world
    submission. Human approval = payment verified out-of-band in the UPI app;
    the floor must only gate UNattended auto-activation."""
    from app.billing import usage

    calls: list[tuple] = []
    monkeypatch.setattr(
        usage, "activate_plan", lambda cid, plan, **kw: calls.append((cid, plan)) or True
    )
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    sub = up.submit_payment("cli_zero", "advanced", "TXN0", amount=0)
    assert sub["status"] == "pending"
    rec = up.decide(sub["id"], True, decided_by="admin")
    assert rec["status"] == "approved"
    assert rec.get("activated") is True
    assert calls == [("cli_zero", "advanced")]


def test_min_plan_price_resolves_voice_and_combo_plans(up):
    """Missing-work audit 2026-07-04: the floor lookup scraped
    get_voice_packages() (single-band payload — voice_b/voice_c never found)
    and get_combo_packages()["plans"] (real key is "tiers" — combo never
    found), so the price floor silently never applied to the most expensive
    plans. Must resolve every paid voice band + combo tier."""
    from app.marketing.combo_packages import COMBO_TIERS
    from app.marketing.voice_packages import BANDS

    for band, info in BANDS.items():
        expected = float(info["price_month"])
        if expected == 0:
            # Freemium ₹0 — no min-price floor applies (fail-open → None)
            assert up._min_plan_price(info["plan_monthly"].lower()) is None, band
            assert up._min_plan_price(info["plan_annual"].lower()) is None, band
            continue
        assert up._min_plan_price(info["plan_monthly"].lower()) == expected, band
        assert up._min_plan_price(info["plan_annual"].lower()) == expected, band
    for tier, info in COMBO_TIERS.items():
        expected = float(info["price_month"])
        assert up._min_plan_price(info["plan_monthly"].lower()) == expected, tier
        assert up._min_plan_price(info["plan_annual"].lower()) == expected, tier


def test_auto_activate_rejects_low_amount_for_voice_and_combo(up, monkeypatch):
    """amount:0 self-serve submit must stay pending for voice B/C and combo
    plans too — not just the marketing plans covered by the 2026-07-01 fix."""
    from app.billing import usage

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    calls: list[tuple] = []
    monkeypatch.setattr(
        usage, "activate_plan", lambda cid, plan, **kw: calls.append((cid, plan)) or True
    )

    for plan in ("voice_b_monthly", "voice_c_monthly", "combo_growth_monthly"):
        out = up.submit_payment(f"cli_{plan}", plan, f"TXN_{plan}", amount=0)
        assert out["status"] == "pending", plan
        assert out["auto_activated"] is False, plan
    assert calls == [], "no below-floor voice/combo submission may activate"


@pytest.fixture
def sp(tmp_path, monkeypatch):
    """sales_pipeline module with its deals store pointed at a tmp file."""
    from app.marketing import sales_pipeline as mod

    monkeypatch.setattr(mod, "_DEALS", str(tmp_path / "deals.jsonl"))
    monkeypatch.setattr(mod, "_ACTIONS", str(tmp_path / "deal_actions.jsonl"))
    return mod


def test_auto_activate_marks_matching_voice_deal_won(up, monkeypatch, sp):
    """A customer Swara closed on a call (deal at 'negotiating', keyed by the
    WhatsApp number she learned) who then actually pays must have that SAME
    deal flipped to 'won' — "finalize the deal" — not left stuck forever."""
    from app.billing import usage

    sp.upsert_deal(
        {"phone": "9876543210", "business_name": "Voice Lead", "niche": "ai_marketing"},
        stage="negotiating",
    )

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    up.submit_payment("cli_voice", "advanced", "TXNVOICE", amount=5999, payer_contact="9876543210")

    deal = sp.list_deals()[0]
    assert deal["stage"] == "won"


def test_decide_approve_marks_matching_voice_deal_won(up, monkeypatch, sp):
    """Same finalization, via the admin-approve path (not just auto-activate)."""
    sp.upsert_deal({"phone": "9123456780", "business_name": "Voice Lead 2"}, stage="negotiating")
    monkeypatch.setattr(up, "_try_activate", lambda cid, plan, amount=0, **kw: True)

    sub = up.submit_payment("cli_voice2", "advanced", "TXNVOICE2", payer_contact="9123456780")
    up.decide(sub["id"], True)

    deal = sp.list_deals()[0]
    assert deal["stage"] == "won"


def test_mark_deal_won_no_matching_deal_is_noop(up, sp):
    """No deal for this phone (e.g. a customer who signed up without ever
    talking to Swara) → silent no-op, never an error."""
    up._mark_deal_won("9000000000")
    assert sp.list_deals() == []


def test_mark_deal_won_never_raises_on_storage_failure(up, monkeypatch):
    from app.marketing import sales_pipeline as sp_mod

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(sp_mod, "list_deals", boom)
    assert up._mark_deal_won("9876543210") is None


def test_mark_deal_won_does_not_resurrect_lost_deal(up, sp):
    """A deal already marked lost must stay lost — a coincidental phone reuse
    (e.g. a different plan/signup) must not silently revive a churned deal."""
    deal = sp.upsert_deal(
        {"phone": "9111111111", "business_name": "Churned Co"}, stage="negotiating"
    )
    sp.set_stage(deal["id"], "lost")

    up._mark_deal_won("9111111111")

    assert sp.list_deals()[0]["stage"] == "lost"
