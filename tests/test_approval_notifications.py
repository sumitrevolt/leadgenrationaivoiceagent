"""Phase-1 idempotent approval-notification tests.

Covers: first send, duplicate suppression, changed approval version, missing
consent, disabled email setting, provider failure + retry, cross-tenant isolation.
Uses injected recipient/consent/send seams + the async test DB session so no real
email is sent and no real store is touched.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.approval_notification import ApprovalNotification
from app.platform import approval_notifier as an


@pytest.fixture(autouse=True)
def _no_real_ledger_writes(monkeypatch):
    """Keep tests hermetic — never touch the real data/delivery_ledger/ files."""
    import app.marketing.delivery_ledger as dl

    monkeypatch.setattr(dl, "log_event", lambda *a, **k: True)


def _approval(client_id="cli-1", aid="apr-1", content=None, status="pending"):
    return {
        "id": aid,
        "client_id": client_id,
        "status": status,
        "content": content if content is not None else {"text": "hello world"},
    }


class Sender:
    """Injectable send_fn spy. Returns (ok, provider_message_id, failure_category)."""

    def __init__(self, ok=True, category="provider_error", pmid="pmid-abc"):
        self.ok = ok
        self.category = category
        self.pmid = pmid
        self.calls: list[dict] = []

    async def __call__(self, to_email, subject, html, text):
        self.calls.append({"to": to_email, "subject": subject})
        return (self.ok, (self.pmid if self.ok else None), ("" if self.ok else self.category))


async def _row(session, key):
    return (
        await session.execute(
            select(ApprovalNotification).where(ApprovalNotification.idempotency_key == key)
        )
    ).scalar_one_or_none()


async def _rowcount(session):
    return (await session.execute(select(func.count(ApprovalNotification.id)))).scalar_one()


_ALLOW = lambda c, e: (True, "")  # noqa: E731


@pytest.mark.parametrize(
    "email",
    (
        "client@upi.local",
        "client@localhost",
        "client@example.com",
        "missing-at-sign",
        "client@invalid",
    ),
)
def test_synthetic_or_invalid_customer_email_is_blocked(email):
    assert an._email_allowed("cli-1", email) == (False, "invalid_email")


def test_recipient_falls_back_to_same_customer_login_email(monkeypatch):
    from app.api import customer_auth
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store,
        "get_client",
        lambda _cid: {"email": "old-placeholder@customer.local"},
    )
    monkeypatch.setattr(
        customer_auth,
        "_read",
        lambda: [
            {"client_id": "other-client", "email": "other@customer.in"},
            {"client_id": "jiya-makeover", "email": "owner@jiya.in"},
        ],
    )

    assert an._resolve_recipient("jiya-makeover") == "owner@jiya.in"


def test_valid_marketing_contact_keeps_precedence(monkeypatch):
    from app.api import customer_auth
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store,
        "get_client",
        lambda _cid: {"contact_email": "marketing@jiya.in"},
    )
    monkeypatch.setattr(
        customer_auth,
        "_read",
        lambda: [{"client_id": "jiya-makeover", "email": "login@jiya.in"}],
    )

    assert an._resolve_recipient("jiya-makeover") == "marketing@jiya.in"


async def test_first_send_records_sent_audit(async_db_session):
    s = Sender(ok=True)
    r = await an.notify_approval(
        _approval(),
        session=async_db_session,
        send_fn=s,
        resolve_recipient=lambda c: "owner@client1.com",
        email_allowed=_ALLOW,
    )
    assert r["status"] == "sent"
    assert len(s.calls) == 1 and s.calls[0]["to"] == "owner@client1.com"
    row = await _row(async_db_session, r["idempotency_key"])
    assert row is not None
    assert row.status == "sent" and row.channel == "email" and row.attempts == 1
    assert row.client_id == "cli-1" and row.approval_id == "apr-1"
    assert row.provider_message_id == "pmid-abc"


async def test_duplicate_send_is_suppressed(async_db_session):
    s = Sender(ok=True)
    a = _approval()
    r1 = await an.notify_approval(
        a,
        session=async_db_session,
        send_fn=s,
        resolve_recipient=lambda c: "x@y.com",
        email_allowed=_ALLOW,
    )
    r2 = await an.notify_approval(
        a,
        session=async_db_session,
        send_fn=s,
        resolve_recipient=lambda c: "x@y.com",
        email_allowed=_ALLOW,
    )
    assert r1["status"] == "sent" and r2["status"] == "sent"
    assert r2.get("note") == "duplicate_suppressed"
    assert len(s.calls) == 1, "email must be sent exactly once for the same approval version"
    assert await _rowcount(async_db_session) == 1  # single audit row


async def test_changed_approval_version_sends_again(async_db_session):
    s = Sender(ok=True)
    a1 = _approval(content={"text": "v1"})
    a2 = _approval(content={"text": "v2 EDITED"})  # same id, changed content => new version
    r1 = await an.notify_approval(
        a1,
        session=async_db_session,
        send_fn=s,
        resolve_recipient=lambda c: "x@y.com",
        email_allowed=_ALLOW,
    )
    r2 = await an.notify_approval(
        a2,
        session=async_db_session,
        send_fn=s,
        resolve_recipient=lambda c: "x@y.com",
        email_allowed=_ALLOW,
    )
    assert r1["status"] == "sent" and r2["status"] == "sent"
    assert r1["idempotency_key"] != r2["idempotency_key"]
    assert len(s.calls) == 2  # a genuinely new version is a new notification
    assert await _rowcount(async_db_session) == 2


async def test_missing_consent_skips_without_send(async_db_session):
    s = Sender(ok=True)
    r = await an.notify_approval(
        _approval(),
        session=async_db_session,
        send_fn=s,
        resolve_recipient=lambda c: "x@y.com",
        email_allowed=lambda c, e: (False, "no_consent"),
    )
    assert r["status"] == "skipped" and r["failure_category"] == "no_consent"
    assert len(s.calls) == 0
    row = await _row(async_db_session, r["idempotency_key"])
    assert row is not None and row.status == "skipped" and row.failure_category == "no_consent"


async def test_disabled_email_setting_skips(async_db_session):
    s = Sender(ok=True)
    r = await an.notify_approval(
        _approval(),
        session=async_db_session,
        send_fn=s,
        resolve_recipient=lambda c: "x@y.com",
        email_allowed=lambda c, e: (False, "email_disabled"),
    )
    assert r["status"] == "skipped" and r["failure_category"] == "email_disabled"
    assert len(s.calls) == 0


async def test_no_email_address_skips(async_db_session):
    s = Sender(ok=True)
    r = await an.notify_approval(
        _approval(),
        session=async_db_session,
        send_fn=s,
        resolve_recipient=lambda c: None,
        email_allowed=_ALLOW,
    )
    assert r["status"] == "skipped" and r["failure_category"] == "no_email"
    assert len(s.calls) == 0


async def test_provider_failure_then_retry_succeeds(async_db_session):
    fail = Sender(ok=False, category="provider_error")
    a = _approval()
    r1 = await an.notify_approval(
        a,
        session=async_db_session,
        send_fn=fail,
        resolve_recipient=lambda c: "x@y.com",
        email_allowed=_ALLOW,
    )
    assert r1["status"] == "failed" and r1["failure_category"] == "provider_error"
    row = await _row(async_db_session, r1["idempotency_key"])
    assert row.status == "failed" and row.attempts == 1

    ok = Sender(ok=True)
    r2 = await an.notify_approval(
        a,
        session=async_db_session,
        send_fn=ok,
        resolve_recipient=lambda c: "x@y.com",
        email_allowed=_ALLOW,
    )
    assert r2["status"] == "sent"  # a failed send is retryable
    assert len(ok.calls) == 1
    row2 = await _row(async_db_session, r2["idempotency_key"])
    assert row2.status == "sent" and row2.attempts == 2  # same row, retried
    assert await _rowcount(async_db_session) == 1


async def test_cross_tenant_recipient_isolation(async_db_session):
    """Each approval is notified to ITS OWN client only — never another tenant."""
    directory = {"cli-1": "owner1@a.com", "cli-2": "owner2@b.com"}
    seen: list[tuple[str, str]] = []

    def resolver(client_id):
        return directory.get(client_id)

    class TrackingSender(Sender):
        async def __call__(self, to_email, subject, html, text):
            seen.append((to_email,))
            return await super().__call__(to_email, subject, html, text)

    s = TrackingSender(ok=True)
    r1 = await an.notify_approval(
        _approval(client_id="cli-1", aid="a1"),
        session=async_db_session,
        send_fn=s,
        resolve_recipient=resolver,
        email_allowed=_ALLOW,
    )
    r2 = await an.notify_approval(
        _approval(client_id="cli-2", aid="a2"),
        session=async_db_session,
        send_fn=s,
        resolve_recipient=resolver,
        email_allowed=_ALLOW,
    )
    assert r1["status"] == "sent" and r2["status"] == "sent"
    assert s.calls[0]["to"] == "owner1@a.com"  # cli-1 approval -> cli-1 email
    assert s.calls[1]["to"] == "owner2@b.com"  # cli-2 approval -> cli-2 email
    row1 = await _row(async_db_session, r1["idempotency_key"])
    row2 = await _row(async_db_session, r2["idempotency_key"])
    assert row1.client_id == "cli-1" and row2.client_id == "cli-2"
    assert row1.idempotency_key != row2.idempotency_key


async def test_sweep_inert_when_flag_off(async_db_session, monkeypatch):
    monkeypatch.delenv("APPROVAL_EMAIL_NOTIFY", raising=False)
    out = await an.notify_pending_approvals(session=async_db_session)
    assert out["enabled"] is False and out["sent"] == 0 and out["seen"] == 0
