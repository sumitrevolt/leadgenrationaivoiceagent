"""UPI/manual activation must create a real Subscription row (audit 2026-07-04).

Pre-fix: usage.activate_plan only set clients_store.plan — after an admin UPI
approval the portal's /api/billing/subscription 404'd (UPI pay-box showed
forever) and reset_usage_period() had no row to write its watermark to.

Real-DB tests (in-memory SQLite, no mocked ORM) — the billing enum bug taught
us mocks miss column/enum semantics.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base


@pytest.fixture
def db_session(monkeypatch):
    """In-memory SQLite session, patched into app.models.base.get_db_session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    @contextmanager
    def _fake_get_db_session():
        yield session

    import app.models.base as base_mod

    monkeypatch.setattr(base_mod, "get_db_session", _fake_get_db_session)
    yield session
    session.close()


@pytest.fixture
def fake_store(monkeypatch):
    """clients_store record for cid 'cli_upi_1' without touching real jsonl."""
    from app.marketing import clients_store

    rec = {
        "id": "cli_upi_1",
        "business_name": "Sharma Salon",
        "email": "sharma@example.com",
        "phone": "9876543210",
        "niche": "salon",
        "city": "Mumbai",
        "plan": "trial",
    }
    monkeypatch.setattr(clients_store, "get_client", lambda cid: rec if cid == rec["id"] else None)
    monkeypatch.setattr(clients_store, "update_client", lambda cid, **kw: rec.update(kw) or rec)
    return rec


def test_ensure_subscription_creates_client_and_active_row(db_session, fake_store):
    from app.billing import usage
    from app.models.client import Client
    from app.models.payment import Subscription, SubscriptionStatus

    ok = usage.activate_plan("cli_upi_1", "starter", ensure_subscription=True)
    assert ok is True

    client = db_session.query(Client).filter(Client.id == "cli_upi_1").one()
    assert client.contact_email == "sharma@example.com"

    sub = db_session.query(Subscription).filter(Subscription.client_id == "cli_upi_1").one()
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.plan_id == "starter"
    assert sub.payment_gateway == "upi"
    assert float(sub.base_price) == 1999.0
    assert sub.billing_cycle.value == "monthly"
    assert sub.current_period_end is not None
    assert (sub.extra_data or {}).get("provisioned_plan") == "starter"


def test_default_call_does_not_create_row(db_session, fake_store):
    """Signup pre-payment provisioning + Stripe/webhook callers keep the old
    behavior — no Subscription row unless explicitly asked for."""
    from app.billing import usage
    from app.models.payment import Subscription

    ok = usage.activate_plan("cli_upi_1", "starter")
    assert ok is True
    assert db_session.query(Subscription).count() == 0


def test_annual_voice_plan_gets_yearly_cycle(db_session, fake_store):
    from app.billing import usage
    from app.models.payment import Subscription

    assert usage.activate_plan("cli_upi_1", "voice_b_annual", ensure_subscription=True)
    sub = db_session.query(Subscription).one()
    assert sub.billing_cycle.value == "yearly"
    assert float(sub.base_price) == 99990.0  # 10x monthly (2 months free)


def test_email_conflict_skips_row_but_still_activates(db_session, fake_store, monkeypatch):
    """Another DB client already owns the email → don't corrupt tenancy: skip
    the Subscription row, but clients_store activation still succeeds."""
    from app.billing import usage
    from app.models.client import Client, ClientStatus
    from app.models.payment import Subscription

    db_session.add(
        Client(
            id="other_client",
            business_name="Other Co",
            contact_name="Other",
            contact_email="sharma@example.com",
            contact_phone="1112223334",
            status=ClientStatus.ACTIVE,
        )
    )
    db_session.flush()

    ok = usage.activate_plan("cli_upi_1", "starter", ensure_subscription=True)
    assert ok is True  # never blocks the payment activation itself
    assert db_session.query(Subscription).count() == 0


def test_reset_usage_period_works_after_ensure(db_session, fake_store):
    """The watermark write that silently no-op'd pre-fix now has a row."""
    from app.billing import usage
    from app.models.payment import Subscription

    usage.activate_plan("cli_upi_1", "advanced", ensure_subscription=True)
    assert usage.reset_usage_period("cli_upi_1") is True
    sub = db_session.query(Subscription).one()
    assert (sub.extra_data or {}).get("usage_period_start")
