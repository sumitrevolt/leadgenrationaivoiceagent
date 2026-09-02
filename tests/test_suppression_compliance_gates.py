"""Compliance gates: unknown-sender opt-out, partial-write recovery, namespaced ids.

Three defects this pins:

1. The junk/bulk guard ran BEFORE any opt-out detection, so an explicit STOP or
   REMOVE from anyone not already held as a prospect was discarded and no
   suppression was written. An opt-out is binding regardless of whether the
   sender is in our database.
2. Ledger write and durable cancellation are two separate writes. A failure
   between them was reported as plain success, hiding a real inconsistency.
3. `event_id` was an unqualified raw id, so the same id from two providers — or
   a bounce and a complaint sharing one message id — collapsed into one event.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.platform import email_unsub, reply_agent
from app.platform.sales_autopilot import followups as _followups
from app.platform.sales_autopilot import store as _sa_store


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(email_unsub, "_store_path", lambda: tmp_path / "email_suppression.jsonl")
    monkeypatch.setattr(_sa_store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(_followups, "_hours_since", lambda _ts: 1e9)
    return tmp_path


# =========================================================== 1. opt-out recognizer
@pytest.mark.parametrize(
    "text",
    [
        "STOP",
        "please REMOVE me from this list",
        "Unsubscribe",
        "opt-out",
        "opt out",
        "do not contact me again",
        "take me off your list",
    ],
)
def test_explicit_optout_recognized(text: str) -> None:
    assert reply_agent._is_explicit_optout("", text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Sure, please stop by the shop tomorrow",  # 'stop by' is not an opt-out
        "Can you send me pricing?",
        "Thanks, will revert",
        "",
    ],
)
def test_ordinary_replies_not_treated_as_optout(text: str) -> None:
    """False positives here would suppress live prospects — worse than a miss."""
    assert reply_agent._is_explicit_optout("", text) is False


def test_quoted_history_does_not_trigger_optout() -> None:
    """Our own footer says 'reply REMOVE' and is quoted back in every reply.

    Scanning the whole body would make every reply look like an opt-out.
    """
    body = (
        "Yes please send the proposal, very interested!\r\n"
        "\r\n"
        "On Mon, 21 Jul 2026, LeadGen AI wrote:\r\n"
        "> Interested? Reply REMOVE to unsubscribe.\r\n"
    )
    assert reply_agent._is_explicit_optout("Re: proposal", body) is False


def test_optout_in_subject_recognized() -> None:
    assert reply_agent._is_explicit_optout("UNSUBSCRIBE", "regards") is True


# ========================================== 2. unknown sender reaches suppression
def _run_triage(monkeypatch, raw: bytes, *, bulk: bool = True) -> dict[str, Any]:
    monkeypatch.setenv("REPLY_AGENT", "1")
    monkeypatch.setenv("SMTP_USER", "admin@leadsgenai.in")
    monkeypatch.setenv("SMTP_PASSWORD", "x")

    class _FakeIMAP:
        def __init__(self, *a: Any, **k: Any) -> None: ...

        def login(self, *a: Any) -> None: ...

        def select(self, *a: Any, **k: Any):
            return ("OK", [b"1"])

        def search(self, *a: Any, **k: Any):
            return ("OK", [b"1"])

        def fetch(self, *a: Any, **k: Any):
            return ("OK", [(b"1 (RFC822", raw)])

        def store(self, *a: Any, **k: Any):
            return ("OK", [b""])

        def close(self) -> None: ...

        def logout(self) -> None: ...

    monkeypatch.setattr(reply_agent.imaplib, "IMAP4_SSL", _FakeIMAP)
    # Sender looks like bulk mail AND is not a known prospect -> the junk guard
    # would previously have discarded it before any opt-out detection.
    monkeypatch.setattr(reply_agent, "_is_bulk_sender", lambda *a, **k: bulk)
    return asyncio.run(reply_agent.run_reply_triage())


def test_unknown_sender_remove_is_not_discarded(monkeypatch) -> None:
    raw = (
        b"From: stranger@nowhere.com\r\n"
        b"Subject: Re: hello\r\n"
        b"Message-ID: <mid-unknown-remove@x>\r\n"
        b"\r\n"
        b"REMOVE me from this list\r\n"
    )
    res = _run_triage(monkeypatch, raw)
    assert email_unsub.is_suppressed("stranger@nowhere.com") is True, (
        f"unknown-sender opt-out was discarded by the junk guard: {res}"
    )
    assert res.get("optout_precheck") == 1


def test_unknown_sender_stop_is_not_discarded(monkeypatch) -> None:
    raw = (
        b"From: stranger2@nowhere.com\r\n"
        b"Subject: Re: hello\r\n"
        b"Message-ID: <mid-unknown-stop@x>\r\n"
        b"\r\n"
        b"STOP\r\n"
    )
    _run_triage(monkeypatch, raw)
    assert email_unsub.is_suppressed("stranger2@nowhere.com") is True


def test_bulk_sender_without_optout_still_skipped(monkeypatch) -> None:
    """Anti-regression: we did not disable the junk guard, only reordered it."""
    raw = (
        b"From: newsletter@bulk.com\r\n"
        b"Subject: Weekly deals\r\n"
        b"Message-ID: <mid-bulk@x>\r\n"
        b"\r\n"
        b"Check out our offers this week!\r\n"
    )
    res = _run_triage(monkeypatch, raw)
    assert email_unsub.is_suppressed("newsletter@bulk.com") is False
    assert res.get("skipped", 0) >= 1


def test_unknown_sender_optout_does_not_create_global_all_outreach(
    monkeypatch, isolated: Path
) -> None:
    """Unresolved identity must NOT be read as licence for a broad record."""
    raw = (
        b"From: stranger3@nowhere.com\r\n"
        b"Subject: unsubscribe\r\n"
        b"Message-ID: <mid-unknown-scope@x>\r\n"
        b"\r\n"
        b"unsubscribe\r\n"
    )
    _run_triage(monkeypatch, raw)
    rows = [
        json.loads(ln)
        for ln in (isolated / "email_suppression.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert rows, "no suppression written"
    # QUARANTINE, not EMAIL_ADDRESS and certainly not ALL_OUTREACH: it blocks
    # just as hard but stays visibly unresolved, so an unreviewed guess is never
    # mistaken for a verified decision.
    assert all(r["scope"] == email_unsub.SCOPE_QUARANTINE for r in rows), (
        f"unresolved identity produced a broader scope than the evidence supports: {rows}"
    )
    assert email_unsub.SCOPE_ALL_OUTREACH not in {r["scope"] for r in rows}
    # ...and the exception is recorded for admin reconciliation.
    exc = isolated / "unresolved_optouts.jsonl"
    assert exc.exists()
    assert "stranger3@nowhere.com" in exc.read_text(encoding="utf-8")


def test_unknown_sender_optout_is_idempotent(monkeypatch, isolated: Path) -> None:
    raw = (
        b"From: stranger4@nowhere.com\r\n"
        b"Subject: stop\r\n"
        b"Message-ID: <mid-unknown-idem@x>\r\n"
        b"\r\n"
        b"stop\r\n"
    )
    _run_triage(monkeypatch, raw)
    _run_triage(monkeypatch, raw)
    rows = [
        ln
        for ln in (isolated / "email_suppression.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(rows) == 1, f"replay produced {len(rows)} rows"


# ================================================= 3. partial-write result model
def _seed(pid: str = "p-gate-1") -> None:
    _sa_store.upsert_prospect(
        {
            "id": pid,
            "email": "gate@b.com",
            "phone": "9876500099",
            "status": "contacted",
            "followup_count": 0,
            "reply_count": 0,
        }
    )


def test_complete_result_when_both_writes_land() -> None:
    _seed()
    r = email_unsub.suppress_with_result(
        "gate@b.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-gate-1"
    )
    assert r == email_unsub.RESULT_COMPLETE


def test_already_applied_on_replay() -> None:
    _seed()
    email_unsub.suppress_with_result(
        "gate@b.com",
        scope=email_unsub.SCOPE_ALL_OUTREACH,
        prospect_id="p-gate-1",
        event_id="evt-gate-1",
    )
    r2 = email_unsub.suppress_with_result(
        "gate@b.com",
        scope=email_unsub.SCOPE_ALL_OUTREACH,
        prospect_id="p-gate-1",
        event_id="evt-gate-1",
    )
    assert r2 == email_unsub.RESULT_ALREADY_APPLIED


def test_cancellation_failure_reports_needs_reconciliation(monkeypatch) -> None:
    """Partial failure must NOT be reported as plain success."""
    _seed()

    def _boom(*_a: Any, **_k: Any):
        raise RuntimeError("prospect store unavailable")

    monkeypatch.setattr(_sa_store, "mark_status", _boom)
    r = email_unsub.suppress_with_result(
        "gate@b.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-gate-1"
    )
    assert r == email_unsub.RESULT_NEEDS_RECONCILIATION


def test_sending_still_blocked_after_partial_failure(monkeypatch) -> None:
    """THE safety property: the ledger is load-bearing, cancellation is metadata."""
    _seed()
    monkeypatch.setattr(
        _sa_store, "mark_status", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
    )
    email_unsub.suppress_with_result(
        "gate@b.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-gate-1"
    )
    # Eligibility-level block still holds even though cancellation failed.
    assert email_unsub.is_suppressed("gate@b.com") is True
    assert email_unsub.is_phone_suppressed(prospect_id="p-gate-1") is True


def test_reconciliation_repairs_partial_failure(monkeypatch) -> None:
    _seed()
    calls = {"n": 0}
    real = _sa_store.mark_status

    def _fail_once(*a: Any, **k: Any):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return real(*a, **k)

    monkeypatch.setattr(_sa_store, "mark_status", _fail_once)
    assert (
        email_unsub.suppress_with_result(
            "gate@b.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-gate-1"
        )
        == email_unsub.RESULT_NEEDS_RECONCILIATION
    )
    assert _sa_store.get_prospect("p-gate-1")["status"] != _sa_store.STATUS_OPTED_OUT

    out = email_unsub.reconcile_suppressions()
    assert out["repaired"] == 1
    assert _sa_store.get_prospect("p-gate-1")["status"] == _sa_store.STATUS_OPTED_OUT


def test_reconciliation_is_idempotent() -> None:
    _seed()
    email_unsub.suppress_with_result(
        "gate@b.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-gate-1"
    )
    first = email_unsub.reconcile_suppressions()
    second = email_unsub.reconcile_suppressions()
    assert first["repaired"] == 0 and first["already_ok"] == 1
    assert second["already_ok"] == 1
    assert _sa_store.get_prospect("p-gate-1")["status"] == _sa_store.STATUS_OPTED_OUT


def test_ledger_write_failure_fails_closed(monkeypatch) -> None:
    """If the ledger itself cannot be written, do NOT report success."""

    def _no_open(*_a: Any, **_k: Any):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", _no_open)
    r = email_unsub.suppress_with_result("fail@b.com", scope=email_unsub.SCOPE_EMAIL_ADDRESS)
    assert r == email_unsub.RESULT_FAILED


# ============================================ 4. namespace-safe idempotency
def test_event_ids_differ_across_providers() -> None:
    a = email_unsub.build_event_id(source="waha", event_type="complaint", raw_id="MSG-1")
    b = email_unsub.build_event_id(source="imap", event_type="complaint", raw_id="MSG-1")
    assert a != b


def test_event_ids_differ_across_event_types() -> None:
    """A bounce and a complaint sharing one message id are DISTINCT events."""
    a = email_unsub.build_event_id(source="imap", event_type="hard_bounce", raw_id="MSG-1")
    b = email_unsub.build_event_id(source="imap", event_type="complaint", raw_id="MSG-1")
    assert a != b


def test_event_ids_differ_across_tenants() -> None:
    a = email_unsub.build_event_id(
        source="imap", event_type="complaint", raw_id="MSG-1", tenant="t-a"
    )
    b = email_unsub.build_event_id(
        source="imap", event_type="complaint", raw_id="MSG-1", tenant="t-b"
    )
    assert a != b


def test_same_context_same_id_is_stable() -> None:
    kw = {"source": "imap", "event_type": "complaint", "raw_id": "MSG-1", "tenant": "t-a"}
    assert email_unsub.build_event_id(**kw) == email_unsub.build_event_id(**kw)


def test_namespaced_ids_do_not_suppress_distinct_events(isolated: Path) -> None:
    """Two genuinely different events with the same raw id must BOTH record."""
    for et in ("hard_bounce", "complaint"):
        email_unsub.suppress(
            "both@b.com",
            reason=et,
            scope=email_unsub.SCOPE_EMAIL_ADDRESS,
            event_id=email_unsub.build_event_id(source="imap", event_type=et, raw_id="MSG-9"),
        )
    rows = [
        ln
        for ln in (isolated / "email_suppression.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(rows) == 2, "namespacing collapsed two distinct events into one"
