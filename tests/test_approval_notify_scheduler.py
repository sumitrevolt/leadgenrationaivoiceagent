"""Phase-1 wiring tests: approval-email sweep scheduler entrypoint.

Covers: scheduler flag off, flag on, overlapping-invocation suppression (lock),
bounded batch, one-client failure isolation, repeated-run idempotency, and health
signal accuracy. Locks are injected so the tests are hermetic (independent of live
Redis) and no real email/store/ledger is touched.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.approval_notification import ApprovalNotification
from app.platform import approval_notifier as an


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    import app.marketing.delivery_ledger as dl

    monkeypatch.setattr(dl, "log_event", lambda *a, **k: True)
    monkeypatch.setenv(
        "APPROVAL_EMAIL_CLIENT_ALLOWLIST",
        ",".join(f"cli-{i}" for i in range(20)),
    )
    an._LOCAL_LOCK["held"] = False


class FreeLock:
    async def acquire(self):
        return True

    async def release(self):
        pass


class HeldLock:
    """Simulates another process already running the sweep."""

    async def acquire(self):
        return False

    async def release(self):
        pass


class Sender:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls: list[str] = []

    async def __call__(self, to_email, subject, html, text):
        self.calls.append(to_email)
        return (self.ok, ("pm" if self.ok else None), ("" if self.ok else "provider_error"))


def _pending(n):
    return [
        {"id": f"a{i}", "client_id": f"cli-{i}", "status": "pending", "content": {"t": i}}
        for i in range(n)
    ]


_ALLOW = lambda c, e: (True, "")  # noqa: E731
_RESOLVE = lambda c: f"{c}@x.com"  # noqa: E731


async def _rowcount(s):
    return (await s.execute(select(func.count(ApprovalNotification.id)))).scalar_one()


async def test_scheduler_flag_off_is_inert(async_db_session, monkeypatch):
    monkeypatch.delenv("APPROVAL_EMAIL_NOTIFY", raising=False)
    s = Sender()
    out = await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), send_fn=s,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )
    assert out["enabled"] is False and out.get("skipped_lock") is False
    assert len(s.calls) == 0
    assert await _rowcount(async_db_session) == 0


async def test_scheduler_flag_on_sends(async_db_session, monkeypatch):
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": _pending(3))
    s = Sender()
    out = await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), send_fn=s,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )
    assert out["enabled"] is True and out["skipped_lock"] is False
    assert out["sent"] == 3 and out["seen"] == 3
    assert len(s.calls) == 3


async def test_enabled_without_allowlist_sends_nothing(async_db_session, monkeypatch):
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.delenv("APPROVAL_EMAIL_CLIENT_ALLOWLIST", raising=False)
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": _pending(3))
    s = Sender()

    out = await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), send_fn=s,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )

    assert out["enabled"] is True
    assert out["seen"] == 0 and out["sent"] == 0
    assert out["not_allowlisted"] == 3
    assert s.calls == []


async def test_multiple_pending_for_same_client_send_one_reminder(async_db_session, monkeypatch):
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.setenv("APPROVAL_EMAIL_CLIENT_ALLOWLIST", "jiya-makeover")
    pending = [
        {"id": f"j{i}", "client_id": "jiya-makeover", "status": "pending", "content": {"t": i}}
        for i in range(22)
    ]
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": pending)
    s = Sender()

    out = await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), send_fn=s,
        resolve_recipient=lambda _cid: "jiya@example.com", email_allowed=_ALLOW,
    )

    assert out["seen"] == 1 and out["sent"] == 1
    assert out["duplicate_client_suppressed"] == 21
    assert len(s.calls) == 1


async def test_overlapping_invocation_suppressed(async_db_session, monkeypatch):
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": _pending(2))
    s = Sender()
    out = await an.run_approval_email_sweep(
        session=async_db_session, lock=HeldLock(), send_fn=s,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )
    assert out["skipped_lock"] is True
    assert len(s.calls) == 0  # nothing sent while another run holds the lock


async def test_bounded_batch_size(async_db_session, monkeypatch):
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": _pending(10))
    s = Sender()
    out = await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), batch_size=4, send_fn=s,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )
    assert out["seen"] == 4 and len(s.calls) == 4  # bounded to batch_size


async def test_one_client_failure_does_not_stop_sweep(async_db_session, monkeypatch):
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": _pending(3))

    class Flaky:
        def __init__(self):
            self.calls: list[str] = []

        async def __call__(self, to_email, subject, html, text):
            self.calls.append(to_email)
            if to_email == "cli-1@x.com":
                raise RuntimeError("provider blew up")
            return (True, "pm", "")

    f = Flaky()
    out = await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), send_fn=f,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )
    assert out["seen"] == 3  # every client processed despite one failure
    assert out["sent"] == 2 and out["failed"] == 1
    assert len(f.calls) == 3


async def test_repeated_run_is_idempotent(async_db_session, monkeypatch):
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": _pending(2))
    s = Sender()
    o1 = await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), send_fn=s,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )
    o2 = await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), send_fn=s,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )
    assert o1["sent"] == 2
    # 2nd run: rows already 'sent' are recognised and NOT re-sent — the provider is
    # never called again for the same approval version (that is the idempotency proof).
    assert len(s.calls) == 2
    assert await _rowcount(async_db_session) == 2


async def test_health_signal_accuracy_and_no_pii(async_db_session, monkeypatch):
    monkeypatch.setenv("APPROVAL_EMAIL_NOTIFY", "1")
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda cid="": _pending(2))
    s = Sender()
    await an.run_approval_email_sweep(
        session=async_db_session, lock=FreeLock(), send_fn=s,
        resolve_recipient=_RESOLVE, email_allowed=_ALLOW,
    )
    h = an.get_health()
    assert h["enabled"] is True
    assert h["sent"] == 2 and h["seen"] == 2 and h["attempted"] == 2
    assert h["last_run"] is not None and h["runs"] >= 1
    # health exposes aggregates + sanitized category only — never an email address
    assert "@x.com" not in str(h)
