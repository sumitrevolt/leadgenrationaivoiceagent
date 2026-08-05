"""GTM P0: paychase Done clears synthetic cards; UPI activate enqueues onboard_client."""

from __future__ import annotations


def _iso_sa_store(tmp_path, monkeypatch):
    from app.platform.sales_autopilot import store as sa_store

    root = tmp_path / "sales_autopilot"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sa_store, "_DIR", str(root))
    monkeypatch.setattr(sa_store, "_PROSPECTS_FILE", str(root / "prospects.json"))
    monkeypatch.setattr(sa_store, "_ATTEMPTS_FILE", str(root / "attempts.jsonl"))
    return sa_store


def test_paychase_done_clears_unpaid_chase_card(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra
    from app.platform.sales_autopilot import pay_truth

    sa_store = _iso_sa_store(tmp_path, monkeypatch)
    sa_store.upsert_prospect(
        {
            "id": "p_chase_1",
            "name": "Estique Test",
            "phone": "9876543210",
            "email": "e@test.in",
            "status": sa_store.STATUS_AWAITING_PAYMENT,
            "converted_client_id": "c_estique",
        }
    )
    cards = pay_truth.unpaid_chase_cards(limit=20)
    assert any(c.get("hq_id") == "paychase:p_chase_1" for c in cards)

    assert ra.mark_handled("paychase:p_chase_1") is True
    cards2 = pay_truth.unpaid_chase_cards(limit=20)
    assert not any(c.get("hq_id") == "paychase:p_chase_1" for c in cards2)


def test_paychase_park_also_hides_card(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra
    from app.platform.sales_autopilot import pay_truth

    sa_store = _iso_sa_store(tmp_path, monkeypatch)
    sa_store.upsert_prospect(
        {
            "id": "p_chase_2",
            "name": "Park Me",
            "phone": "9123456780",
            "status": sa_store.STATUS_AWAITING_PAYMENT,
        }
    )
    assert ra.park_for_admin("paychase:p_chase_2", note="later") is True
    assert not any(c.get("hq_id") == "paychase:p_chase_2" for c in pay_truth.unpaid_chase_cards())


def test_upi_activate_enqueues_onboard_client(monkeypatch, tmp_path):
    import app.platform.upi_payments as upi_mod
    import app.tasks.staff_jobs as sj

    monkeypatch.setattr(upi_mod, "_STORE", lambda: str(tmp_path / "upi.json"))
    delayed: list[tuple] = []

    class _FakeTask:
        @staticmethod
        def delay(cid, send_welcome=True):
            delayed.append((cid, send_welcome))

    monkeypatch.setattr(sj, "onboard_client", _FakeTask)
    monkeypatch.setattr(upi_mod, "_try_activate", lambda *a, **k: True)
    monkeypatch.setattr(upi_mod, "_mark_deal_won", lambda *_a: None)
    monkeypatch.setattr(upi_mod, "_fire_gst_invoice", lambda *_a: None)
    monkeypatch.setattr(upi_mod, "_notify_admin", lambda *_a, **_k: None)

    sub = upi_mod.submit_payment(
        client_id="c_new_paid", plan="starter", upi_ref="UPIREVG1", amount=1999
    )
    assert sub.get("ok") is True
    # Keep auto-activate OFF so decide path owns activation
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)
    out = upi_mod.decide(sub["id"], approve=True, decided_by="admin")
    assert out.get("activated") is True
    assert delayed == [("c_new_paid", False)]
