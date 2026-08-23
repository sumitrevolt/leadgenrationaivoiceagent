"""Trial-to-paid nudge (BLK-02) contract tests — TRIAL_NUDGE_ENABLED INERT default.

Contract locks:
  - OFF default: bina flag zero sends, zero writes (fail-closed).
  - HARD_OFF precedence over ENABLED.
  - Paid/active client KABHI eligible nahi (billing-truth gate).
  - Suppression wins (DPDP opt-out).
  - Idempotency/cooldown via client-record stamps (koi double-send nahi).
  - Price single-source = marketing/packages.py (billing truth).
  - WhatsApp text sirf OWNER ke liye — koi auto-send path NAHI.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.billing import trial_nudge as tn


def _client(
    cid: str = "c1",
    *,
    trial: bool = True,
    days_left: float = 1,
    status: str = "",
    email: str | None = "owner@biz.com",
    **extra,
) -> dict:
    c: dict = {"id": cid, "business_name": "Test Biz", "status": status}
    if email is not None:
        c["email"] = email
    if trial:
        exp = datetime.now(timezone.utc) + timedelta(days=days_left)
        c["trial"] = True
        c["trial_expires"] = exp.isoformat()
    c.update(extra)
    return c


class FakeStore:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.updates: list[tuple[str, dict]] = []

    def list_clients(self) -> list[dict]:
        return [dict(r) for r in self.rows]

    def update_client(self, cid: str, **fields):
        self.updates.append((cid, fields))
        for r in self.rows:
            if str(r.get("id")) == str(cid):
                r.update(fields)
                return r
        return None


@pytest.fixture()
def wired(monkeypatch):
    """Fake clients_store + suppressed set + sent-log; returns handles."""

    class Handles:
        def __init__(self):
            self.store: FakeStore | None = None
            self.sent: list[tuple[str, str]] = []
            self.suppressed: set[str] = set()

        def set_clients(self, rows: list[dict]) -> FakeStore:
            self.store = FakeStore(rows)
            from app.marketing import clients_store

            monkeypatch.setattr(clients_store, "list_clients", self.store.list_clients)
            monkeypatch.setattr(clients_store, "update_client", self.store.update_client)
            return self.store

        async def _send(self, to_email: str, subject: str, body: str) -> bool:
            self.sent.append((to_email, subject))
            return True

    from app.platform import email_unsub as eu

    h = Handles()

    def _is_suppressed(email: str) -> bool:
        return str(email or "").lower() in h.suppressed

    monkeypatch.setattr(eu, "is_suppressed", _is_suppressed)
    return h


def _run(h, **kw) -> dict:
    return asyncio.run(tn.run_trial_nudge(send_fn=h._send, **kw))


# ---------------------------------------------------------------- INERT gates


def test_inert_by_default(wired, monkeypatch):
    monkeypatch.delenv("TRIAL_NUDGE_ENABLED", raising=False)
    monkeypatch.delenv("TRIAL_NUDGE_HARD_OFF", raising=False)
    wired.set_clients([_client()])
    out = _run(wired)
    assert out["sent"] == 0
    assert out["skip_reason"] == "trial_nudge_disabled"
    assert wired.sent == []
    assert wired.store.updates == []


def test_hard_off_blocks_even_when_enabled(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    monkeypatch.setenv("TRIAL_NUDGE_HARD_OFF", "1")
    wired.set_clients([_client()])
    out = _run(wired)
    assert out["skip_reason"] == "trial_nudge_hard_off"
    assert wired.sent == []


# ---------------------------------------------------------------- eligibility


def test_expiring_trial_sent_and_stamped(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    wired.set_clients([_client(days_left=1)])
    out = _run(wired)
    assert out["sent"] == 1 and len(wired.sent) == 1
    assert out["items"][0]["stage"] == "expiring"
    cid, fields = wired.store.updates[0]
    assert cid == "c1"
    assert fields["trial_nudge_stage"] == "expiring"
    assert fields["trial_nudge_count"] == 1
    assert fields["trial_nudge_at"]
    # Owner WA text present but nothing auto-sent beyond email rail.
    assert out["items"][0]["wa_text_owner_1click"]


def test_expired_trial_stage(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    wired.set_clients([_client(days_left=-2)])
    out = _run(wired)
    assert out["sent"] == 1
    assert out["items"][0]["stage"] == "expired"


def test_active_client_never_nudged(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    wired.set_clients([_client(status="active")])
    out = _run(wired)
    assert out["sent"] == 0
    assert out["skipped_active"] == 1
    assert wired.sent == []


def test_not_due_trial_skipped(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    wired.set_clients([_client(days_left=6)])  # > default TRIAL_NUDGE_DAYS_BEFORE=2
    out = _run(wired)
    assert out["sent"] == 0
    assert out["skipped_not_due"] == 1


def test_phone_only_client_skipped(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    wired.set_clients([_client(email=None, phone="919999900000")])
    out = _run(wired)
    assert out["sent"] == 0
    assert out["skipped_no_email"] == 1


# -------------------------------------------------------------------- safety


def test_suppression_wins(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    wired.set_clients([_client()])
    wired.suppressed.add("owner@biz.com")
    out = _run(wired)
    assert out["sent"] == 0
    assert out["skipped_suppressed"] == 1
    assert wired.store.updates == []


# ------------------------------------------------------- idempotency/cooldown


def test_cooldown_no_double_send_same_day(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    wired.set_clients(
        [_client(trial_nudge_stage="expiring", trial_nudge_at=recent, trial_nudge_count=1)]
    )
    out = _run(wired)
    assert out["sent"] == 0
    assert out["skipped_cooldown"] == 1


def test_max_per_client_cap(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    wired.set_clients(
        [_client(trial_nudge_stage="expired", trial_nudge_at=old, trial_nudge_count=3)]
    )
    out = _run(wired)
    assert out["sent"] == 0
    assert out["skipped_cooldown"] == 1


def test_batch_limit(wired, monkeypatch):
    monkeypatch.setenv("TRIAL_NUDGE_ENABLED", "1")
    wired.set_clients([_client(f"c{i}") for i in range(8)])
    out = _run(wired, limit=3)
    assert out["sent"] == 3


# ------------------------------------------------------- billing-truth contract


def test_price_single_source_packages(monkeypatch):
    from app.marketing.packages import get_starter_price_inr

    expected = int(get_starter_price_inr())
    assert tn.starter_price_inr() == expected
    msg = tn.build_message("expired", "Biz", 0, price=tn.starter_price_inr())
    assert f"₹{expected:,}" in msg["body"]
    assert "₹1,999" not in msg["body"] or expected == 1999  # hardcoded drift-guard


def test_messages_contain_pricing_url_and_unsub():
    for stage in ("expiring", "expired"):
        msg = tn.build_message(stage, "Biz", 2)
        assert "leadsgenai.in/pricing" in msg["body"]
        assert "unsubscribe" in msg["body"].lower()


# ------------------------------------------------------------ WA ban-safety


def test_no_whatsapp_send_path_in_module():
    src = inspect.getsource(tn)
    assert "integrations.whatsapp" not in src
    assert "import whatsapp" not in src
