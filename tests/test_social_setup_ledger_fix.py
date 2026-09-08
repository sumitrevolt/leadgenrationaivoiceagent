"""Regression: saving social config must record the `social_setup_completed`
delivery-ledger milestone (customer-visible timeline proof).

Before this fix, app.api.customer_dashboard._sync_social_delivery_stage called
delivery_ledger.log_event(..., customer_visible=True) — but log_event has NO
`customer_visible` param, so it raised TypeError which the surrounding
`except: pass` swallowed → the "socials connected" milestone was silently
missing from every customer's timeline. RED-first: on the unfixed code these
tests fail (no event lands).
"""


def test_social_config_save_records_setup_completed(monkeypatch, tmp_path):
    from app.api import customer_dashboard
    from app.marketing import delivery_ledger

    # Isolate the ledger to a tmp dir (_LEDGER_DIR is a call-time resolver).
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "ledger"))

    cid = "client_social_test"
    cfg = {"handles": {"instagram": "@testbiz", "facebook": "", "gbp": ""}}
    customer_dashboard._sync_social_delivery_stage(cid, cfg)

    events = [e.get("event") for e in delivery_ledger._read_events(cid)]
    assert "social_setup_completed" in events


def test_no_social_handles_skips_event(monkeypatch, tmp_path):
    from app.api import customer_dashboard
    from app.marketing import delivery_ledger

    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "ledger"))
    cid = "client_no_social"
    customer_dashboard._sync_social_delivery_stage(cid, {"handles": {}})
    events = [e.get("event") for e in delivery_ledger._read_events(cid)]
    assert "social_setup_completed" not in events


def test_idempotent_no_duplicate_on_resave(monkeypatch, tmp_path):
    from app.api import customer_dashboard
    from app.marketing import delivery_ledger

    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "ledger"))
    cid = "client_resave"
    cfg = {"handles": {"instagram": "@x"}}
    customer_dashboard._sync_social_delivery_stage(cid, cfg)
    customer_dashboard._sync_social_delivery_stage(cid, cfg)  # re-save
    events = [e.get("event") for e in delivery_ledger._read_events(cid)]
    assert events.count("social_setup_completed") == 1
