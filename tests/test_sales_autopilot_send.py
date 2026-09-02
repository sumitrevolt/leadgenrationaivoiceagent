"""Sales Autopilot — idempotent send service (dry-run default, no provider call)."""

from __future__ import annotations

import asyncio

import pytest

from app.platform.sales_autopilot import eligibility as elig
from app.platform.sales_autopilot import policy as policy_mod
from app.platform.sales_autopilot import send as send_mod
from app.platform.sales_autopilot import store as store


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(policy_mod, "_POLICY_DIR", str(tmp_path))
    monkeypatch.setattr(policy_mod, "_POLICY_FILE", str(tmp_path / "policy.json"))
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    monkeypatch.setattr(elig, "_owner_kill", lambda name: False)
    monkeypatch.setattr(elig, "_is_suppressed", lambda phone: False)
    # Always inside business hours for the send tests.
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(
        elig,
        "_now_ist",
        lambda: datetime(2026, 7, 24, 12, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    )
    yield


def _seed():
    return store.upsert_prospect(
        {
            "id": "p-send-1",
            "name": "Glow Studio",
            "phone": "+919812345678",
            "city": "Mumbai",
            "niche": "beauty_makeover",
            "consent_basis": "inquiry_form",
            "status": store.STATUS_NEW,
        }
    )


def test_dry_run_default_no_provider_call(monkeypatch):
    _seed()
    called = {"n": 0}

    async def _boom(phone, message):
        called["n"] += 1
        return {"sent": True}

    from app.marketing import whatsapp_campaign

    monkeypatch.setattr(whatsapp_campaign, "send_one", _boom)

    res = asyncio.run(send_mod.send("p-send-1", channel="whatsapp", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.SIMULATED
    assert called["n"] == 0  # provider NEVER called in dry-run
    assert res["dry_run"] is True


def test_idempotent_duplicate(monkeypatch):
    _seed()
    r1 = asyncio.run(send_mod.send("p-send-1", channel="whatsapp", step=elig.STEP_INITIAL))
    assert r1["outcome"] == send_mod.SIMULATED
    # Re-seed to NEW so eligibility would pass again — but idempotency must block replay.
    store.mark_status("p-send-1", store.STATUS_NEW, steps_done=[])
    r2 = asyncio.run(send_mod.send("p-send-1", channel="whatsapp", step=elig.STEP_INITIAL))
    assert r2["outcome"] == send_mod.DUPLICATE


def test_blocked_when_ineligible(monkeypatch):
    store.upsert_prospect(
        {"id": "p-x", "phone": "+919812345000", "niche": "x", "status": store.STATUS_NEW}
    )  # no consent_basis
    res = asyncio.run(send_mod.send("p-x", channel="whatsapp", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.BLOCKED
    assert res["reason"] == elig.INELIGIBLE


def test_live_send_only_when_flag_and_dry_run_false(monkeypatch):
    _seed()
    sent = {"n": 0}

    async def _ok(phone, message):
        sent["n"] += 1
        return {"sent": True, "mode": "cloud_api"}

    from app.marketing import whatsapp_campaign

    monkeypatch.setattr(whatsapp_campaign, "send_one", _ok)
    # Arm channel + dry_run false.
    monkeypatch.setenv("SALES_AUTOPILOT_WHATSAPP_ENABLED", "1")
    policy_mod.save_policy({"dry_run": False, "whatsapp_enabled": True})
    monkeypatch.setenv("SALES_AUTOPILOT_DRY_RUN", "0")

    res = asyncio.run(send_mod.send("p-send-1", channel="whatsapp", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.SENT
    assert sent["n"] == 1


def test_provider_timeout_no_retry(monkeypatch):
    _seed()

    async def _timeout(phone, message, timeout_s):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(send_mod, "_provider_send_whatsapp", _timeout)
    monkeypatch.setenv("SALES_AUTOPILOT_WHATSAPP_ENABLED", "1")
    policy_mod.save_policy({"dry_run": False, "whatsapp_enabled": True})
    monkeypatch.setenv("SALES_AUTOPILOT_DRY_RUN", "0")

    res = asyncio.run(send_mod.send("p-send-1", channel="whatsapp", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.UNKNOWN_REQUIRES_REVIEW
    assert res["reason"] == "provider_timeout_no_retry"


def test_attempt_persisted_before_provider(monkeypatch):
    _seed()
    res = asyncio.run(send_mod.send("p-send-1", channel="whatsapp", step=elig.STEP_INITIAL))
    idem = res["idempotency_key"]
    assert store.attempt_exists(idem)
    att = store.get_attempt(idem)
    assert att is not None


def _seed_email():
    return store.upsert_prospect(
        {
            "id": "p-email-1",
            "name": "Glow Studio",
            "email": "glow@example.com",
            "phone": "+919812345678",
            "city": "Mumbai",
            "niche": "beauty_makeover",
            "consent_basis": "inquiry_form",
            "status": store.STATUS_NEW,
        }
    )


def _arm_email_live(monkeypatch):
    monkeypatch.setenv("SALES_AUTOPILOT_EMAIL_ENABLED", "1")
    policy_mod.save_policy({"dry_run": False, "email_enabled": True, "whatsapp_enabled": False})
    monkeypatch.setenv("SALES_AUTOPILOT_DRY_RUN", "0")


def test_email_disabled_flag_sends_zero(monkeypatch):
    """Channel/policy off ⇒ SIMULATED; EmailSender never called."""
    _seed_email()
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True, "mode": "email_sender", "provider_called": True}

    monkeypatch.setattr(send_mod, "_provider_send_email", _boom)
    # Engine on but email channel off (default dry_run / channel gate).
    res = asyncio.run(send_mod.send("p-email-1", channel="email", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.SIMULATED
    assert called["n"] == 0


def test_email_suppressed_sends_zero(monkeypatch):
    _seed_email()
    _arm_email_live(monkeypatch)
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True, "mode": "email_sender", "provider_called": True}

    monkeypatch.setattr(send_mod, "_provider_send_email", _boom)
    monkeypatch.setattr(send_mod, "_suppressed_now", lambda *a, **k: True)

    res = asyncio.run(send_mod.send("p-email-1", channel="email", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.SKIPPED
    assert res["reason"] == "suppressed_pre_provider"
    assert called["n"] == 0


def test_email_duplicate_sends_once(monkeypatch):
    _seed_email()
    _arm_email_live(monkeypatch)
    sent = {"n": 0}

    async def _ok(*a, **k):
        sent["n"] += 1
        return {"sent": True, "mode": "email_sender", "provider_called": True}

    monkeypatch.setattr(send_mod, "_provider_send_email", _ok)
    r1 = asyncio.run(send_mod.send("p-email-1", channel="email", step=elig.STEP_INITIAL))
    assert r1["outcome"] == send_mod.SENT
    store.mark_status("p-email-1", store.STATUS_NEW, steps_done=[])
    r2 = asyncio.run(send_mod.send("p-email-1", channel="email", step=elig.STEP_INITIAL))
    assert r2["outcome"] == send_mod.DUPLICATE
    assert sent["n"] == 1


def test_email_missing_smtp_fails_closed(monkeypatch):
    _seed_email()
    _arm_email_live(monkeypatch)

    async def _no_smtp(*a, **k):
        return {"sent": False, "mode": "smtp_not_configured", "provider_called": False}

    monkeypatch.setattr(send_mod, "_provider_send_email", _no_smtp)
    res = asyncio.run(send_mod.send("p-email-1", channel="email", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.FAILED
    assert res["reason"] == "smtp_not_configured"
    assert res["provider"]["provider_called"] is False


def test_email_timeout_unknown_no_retry(monkeypatch):
    _seed_email()
    _arm_email_live(monkeypatch)

    async def _timeout(*a, **k):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(send_mod, "_provider_send_email", _timeout)
    res = asyncio.run(send_mod.send("p-email-1", channel="email", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.UNKNOWN_REQUIRES_REVIEW
    assert res["reason"] == "provider_timeout_no_retry"


def test_email_bulk_input_refuses(monkeypatch):
    store.upsert_prospect(
        {
            "id": "p-bulk",
            "email": "a@x.com,b@y.com",
            "niche": "beauty_makeover",
            "consent_basis": "inquiry_form",
            "status": store.STATUS_NEW,
        }
    )
    _arm_email_live(monkeypatch)
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True, "mode": "email_sender", "provider_called": True}

    monkeypatch.setattr(send_mod, "_provider_send_email", _boom)
    res = asyncio.run(send_mod.send("p-bulk", channel="email", step=elig.STEP_INITIAL))
    assert res["outcome"] == send_mod.SKIPPED
    assert res["reason"] == "bulk_or_invalid_email_refused"
    assert called["n"] == 0
    assert res["provider"]["provider_called"] is False


def test_provider_send_email_one_to_one_helper():
    assert send_mod._email_contact_is_one_to_one("owner@example.com") is True
    assert send_mod._email_contact_is_one_to_one("a@x.com,b@y.com") is False
    assert send_mod._email_contact_is_one_to_one("") is False
