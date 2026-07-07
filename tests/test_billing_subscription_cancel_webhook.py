"""subscription.cancelled was the only SUPPORTED_EVENTS type with zero emit
call-sites anywhere in the app (grep audit 2026-07-07) — a customer who
registered a "subscription.cancelled" webhook would never receive it, and
FLOW_RUNNER event-triggered flows on that event could never fire. Fix:
cancel_subscription() now fires it via the existing _emit_billing_customer_webhook
helper (same chokepoint activate_plan already uses for payment/activation).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import billing
from app.api.billing_models import CancelSubscriptionRequest


def _fake_subscription():
    sub = MagicMock()
    sub.id = "sub_123"
    sub.stripe_subscription_id = None
    sub.current_period_end = datetime.utcnow() + timedelta(days=10)
    return sub


async def test_cancel_subscription_emits_subscription_cancelled(monkeypatch):
    sub = _fake_subscription()
    result = MagicMock()
    result.scalar_one_or_none.return_value = sub
    db = AsyncMock()
    db.execute.return_value = result

    emitted = []
    monkeypatch.setattr(
        billing,
        "_emit_billing_customer_webhook",
        lambda cid, ev, payload: emitted.append((cid, ev, payload)),
    )

    req = CancelSubscriptionRequest(reason="too expensive", cancel_immediately=False)
    out = await billing.cancel_subscription(req, client_id="client9", db=db)

    assert out["success"] is True
    assert len(emitted) == 1
    cid, event, payload = emitted[0]
    assert cid == "client9"
    assert event == "subscription.cancelled"
    assert payload["subscription_id"] == "sub_123"
    assert payload["reason"] == "too expensive"
    db.commit.assert_awaited_once()


async def test_cancel_subscription_no_active_subscription_no_emit(monkeypatch):
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result

    emitted = []
    monkeypatch.setattr(
        billing,
        "_emit_billing_customer_webhook",
        lambda *a, **k: emitted.append(1),
    )

    req = CancelSubscriptionRequest(reason="", cancel_immediately=True)
    with pytest.raises(Exception):
        await billing.cancel_subscription(req, client_id="client9", db=db)
    assert emitted == [], "no webhook when there was nothing to cancel"
