"""Studio entitlement gate + combo router gate (audit 2026-07-04 follow-on).

- STUDIO_ENTITLEMENT_GATE (default OFF): expired trials and never-paid
  paid-plan signups (7-day grace) get 402 from the studio; every lookup
  failure fails OPEN (a DB hiccup must never lock out a paying customer).
- COMBO_PRODUCT (default OFF): the public /api/combo surface leaked the
  hidden legacy `growth` plan + forbidden bundle-USP framing (ADR-009) —
  router must NOT be mounted unless explicitly enabled.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.customer_marketing_studio import _entitlement_gate


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_gate_off_allows_everything(monkeypatch):
    monkeypatch.delenv("STUDIO_ENTITLEMENT_GATE", raising=False)
    _entitlement_gate("c1", {"trial": True, "trial_expires": _iso(datetime(2020, 1, 1))})


def test_expired_trial_blocked(monkeypatch):
    monkeypatch.setenv("STUDIO_ENTITLEMENT_GATE", "1")
    with pytest.raises(HTTPException) as ei:
        _entitlement_gate(
            "c1",
            {"trial": True, "trial_expires": _iso(datetime.utcnow() - timedelta(days=1))},
        )
    assert ei.value.status_code == 402


def test_active_trial_allowed(monkeypatch):
    monkeypatch.setenv("STUDIO_ENTITLEMENT_GATE", "1")
    _entitlement_gate(
        "c1",
        {"trial": True, "trial_expires": _iso(datetime.utcnow() + timedelta(days=3))},
    )


def test_paid_plan_with_active_subscription_allowed(monkeypatch):
    monkeypatch.setenv("STUDIO_ENTITLEMENT_GATE", "1")
    from app.models.payment import SubscriptionStatus

    class _Sub:
        status = SubscriptionStatus.ACTIVE

    import app.billing.usage as usage

    monkeypatch.setattr(usage, "_latest_subscription", lambda db, cid: _Sub())
    _entitlement_gate(
        "c1",
        {"plan": "starter", "created_at": _iso(datetime.utcnow() - timedelta(days=30))},
    )


def test_never_paid_signup_blocked_after_grace(monkeypatch):
    monkeypatch.setenv("STUDIO_ENTITLEMENT_GATE", "1")
    from contextlib import contextmanager

    import app.billing.usage as usage
    import app.models.base as models_base

    monkeypatch.setattr(usage, "_latest_subscription", lambda db, cid: None)

    # Hermetic: gate DB-error pe FAIL-OPEN hai (design) — CI me DB na hone se
    # get_db_session raise → allow → DID-NOT-RAISE. Working session-stub do taaki
    # test gate-LOGIC test kare, DB-availability nahi.
    @contextmanager
    def _fake_db_session():
        yield None

    monkeypatch.setattr(models_base, "get_db_session", _fake_db_session)
    with pytest.raises(HTTPException) as ei:
        _entitlement_gate(
            "c1",
            {"plan": "starter", "created_at": _iso(datetime.utcnow() - timedelta(days=8))},
        )
    assert ei.value.status_code == 402


def test_fresh_signup_within_grace_allowed(monkeypatch):
    monkeypatch.setenv("STUDIO_ENTITLEMENT_GATE", "1")
    import app.billing.usage as usage

    monkeypatch.setattr(usage, "_latest_subscription", lambda db, cid: None)
    _entitlement_gate(
        "c1",
        {"plan": "starter", "created_at": _iso(datetime.utcnow() - timedelta(days=2))},
    )


def test_sub_lookup_error_fails_open(monkeypatch):
    monkeypatch.setenv("STUDIO_ENTITLEMENT_GATE", "1")
    import app.billing.usage as usage

    def _boom(db, cid):
        raise RuntimeError("db down")

    monkeypatch.setattr(usage, "_latest_subscription", _boom)
    _entitlement_gate(
        "c1",
        {"plan": "starter", "created_at": _iso(datetime.utcnow() - timedelta(days=30))},
    )


def test_combo_router_not_mounted_by_default():
    """COMBO_PRODUCT unset -> no /api/combo/* routes registered (leak closed)."""
    import os

    assert (os.environ.get("COMBO_PRODUCT", "0") or "0").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ), "test assumes default env"
    from app.main import app

    combo_paths = [
        getattr(r, "path", "") for r in app.routes if "/api/combo" in getattr(r, "path", "")
    ]
    assert combo_paths == [], f"combo routes leaked: {combo_paths}"
