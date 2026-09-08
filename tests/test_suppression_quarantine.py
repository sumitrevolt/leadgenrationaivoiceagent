"""Unresolved opt-outs are a QUARANTINE, not a silent permanent decision.

When someone says STOP but we cannot tie the request to a tenant or prospect,
two things must both be true:

  * sending to that destination stops immediately (fail-closed), and
  * the record stays visibly UNRESOLVED, so an admin is prompted to reconcile.

Collapsing that into an ordinary permanent suppression would make an unreviewed
guess indistinguishable from a verified opt-out, and nothing would ever prompt
anyone to resolve it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.platform import email_unsub, reply_agent
from app.platform.sales_autopilot import store as _sa_store


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(email_unsub, "_store_path", lambda: tmp_path / "email_suppression.jsonl")
    monkeypatch.setattr(_sa_store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    return tmp_path


def _triage(monkeypatch, sender: str, mid: str, text: str = "STOP") -> dict[str, Any]:
    raw = (f"From: {sender}\r\nSubject: Re: hi\r\nMessage-ID: <{mid}>\r\n\r\n{text}\r\n").encode()

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

    monkeypatch.setenv("REPLY_AGENT", "1")
    monkeypatch.setenv("SMTP_USER", "admin@leadsgenai.in")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    monkeypatch.setattr(reply_agent.imaplib, "IMAP4_SSL", _FakeIMAP)
    monkeypatch.setattr(reply_agent, "_is_bulk_sender", lambda *a, **k: True)
    return asyncio.run(reply_agent.run_reply_triage())


# ------------------------------------------- unresolved identity -> quarantine
def test_unresolved_optout_creates_quarantine_not_permanent(monkeypatch, isolated: Path) -> None:
    _triage(monkeypatch, "ghost@nowhere.com", "q-1")
    rows = [
        json.loads(ln)
        for ln in (isolated / "email_suppression.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert rows, "no suppression written"
    assert all(r["scope"] == email_unsub.SCOPE_QUARANTINE for r in rows), rows
    assert email_unsub.suppression_state(email="ghost@nowhere.com") == email_unsub.STATE_QUARANTINE


def test_quarantine_blocks_sending(monkeypatch) -> None:
    """Fail-closed: an open question still stops the send."""
    _triage(monkeypatch, "ghost2@nowhere.com", "q-2")
    assert email_unsub.is_suppressed("ghost2@nowhere.com") is True
    assert email_unsub.is_contact_suppressed(email="ghost2@nowhere.com", channel="email") is True


def test_quarantine_is_surfaced_for_admin(monkeypatch) -> None:
    _triage(monkeypatch, "ghost3@nowhere.com", "q-3")
    open_items = email_unsub.list_quarantined()
    assert any(r["email"] == "ghost3@nowhere.com" for r in open_items)


def test_quarantine_does_not_block_unrelated_whatsapp(monkeypatch) -> None:
    """We only know an email address — a phone must not be silenced by guess."""
    _triage(monkeypatch, "ghost4@nowhere.com", "q-4")
    assert email_unsub.is_phone_suppressed(phone="9876500123") is False


# ------------------------------------------- known prospect -> settled record
def test_known_prospect_optout_is_permanent_not_quarantine(monkeypatch) -> None:
    email_unsub.suppress("known@b.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-known")
    assert (
        email_unsub.suppression_state(email="known@b.com", prospect_id="p-known")
        == email_unsub.STATE_PERMANENT
    )


def test_permanent_outranks_quarantine(monkeypatch) -> None:
    """A settled decision must not be downgraded by a stray hold."""
    email_unsub.suppress("mix@b.com", scope=email_unsub.SCOPE_QUARANTINE)
    email_unsub.suppress("mix@b.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-mix")
    assert email_unsub.suppression_state(email="mix@b.com") == email_unsub.STATE_PERMANENT


def test_clean_address_has_no_state() -> None:
    assert email_unsub.suppression_state(email="clean@b.com") == email_unsub.STATE_NONE


# ----------------------------------------------------- resolution lifecycle
def test_resolve_quarantine_to_permanent_is_idempotent(monkeypatch) -> None:
    _triage(monkeypatch, "ghost5@nowhere.com", "q-5")
    first = email_unsub.resolve_quarantine("ghost5@nowhere.com", resolution="suppress")
    assert first == email_unsub.RESULT_COMPLETE
    assert email_unsub.suppression_state(email="ghost5@nowhere.com") == email_unsub.STATE_PERMANENT
    second = email_unsub.resolve_quarantine("ghost5@nowhere.com", resolution="suppress")
    assert second == email_unsub.RESULT_ALREADY_APPLIED
    # Still blocked either way.
    assert email_unsub.is_suppressed("ghost5@nowhere.com") is True


def test_release_requires_explicit_evidence(monkeypatch) -> None:
    """Releasing a hold a real person asked for is the one irreversible mistake."""
    _triage(monkeypatch, "ghost6@nowhere.com", "q-6")
    refused = email_unsub.resolve_quarantine("ghost6@nowhere.com", resolution="released")
    assert refused == email_unsub.RESULT_FAILED
    assert email_unsub.is_suppressed("ghost6@nowhere.com") is True


def test_release_with_evidence_unblocks(monkeypatch) -> None:
    _triage(monkeypatch, "ghost7@nowhere.com", "q-7")
    ok = email_unsub.resolve_quarantine(
        "ghost7@nowhere.com",
        resolution="released",
        evidence="verified false positive: autoresponder quoting our footer",
        resolved_by="sumit",
    )
    assert ok == email_unsub.RESULT_COMPLETE
    assert email_unsub.is_suppressed("ghost7@nowhere.com") is False
    assert email_unsub.suppression_state(email="ghost7@nowhere.com") == email_unsub.STATE_NONE


def test_released_quarantine_leaves_audit_trail(monkeypatch, isolated: Path) -> None:
    """Release appends evidence; it never deletes the original hold."""
    _triage(monkeypatch, "ghost8@nowhere.com", "q-8")
    email_unsub.resolve_quarantine(
        "ghost8@nowhere.com", resolution="released", evidence="confirmed bot"
    )
    text = (isolated / "email_suppression.jsonl").read_text(encoding="utf-8")
    assert "confirmed bot" in text
    assert text.count("ghost8@nowhere.com") >= 2, "original hold was not preserved"


def test_resolution_field_survives_read_back(isolated: Path) -> None:
    """Regression for the fixed-key-set bug that dropped new fields on read."""
    email_unsub.suppress("rt@b.com", scope=email_unsub.SCOPE_QUARANTINE)
    email_unsub.resolve_quarantine("rt@b.com", resolution="released", evidence="e")
    rows = email_unsub._iter_suppression_rows()
    assert any(r.get("resolution") == "released" for r in rows)


# ------------------------------------------------------ tenant separation
def test_same_address_two_tenants_quarantine_is_destination_scoped() -> None:
    """An exact-destination hold is intentionally destination-wide.

    The mailbox owner asked to stop; that request is not tenant-specific. What
    must NOT happen is a tenant-A hold silently becoming a cross-channel opt-out
    for a tenant-B contact.
    """
    email_unsub.suppress("shared@b.com", scope=email_unsub.SCOPE_QUARANTINE, tenant="tenant-a")
    assert email_unsub.is_suppressed("shared@b.com") is True
    assert email_unsub.is_phone_suppressed(prospect_id="tenant-b-contact") is False
    assert email_unsub.suppression_state(email="shared@b.com") == email_unsub.STATE_QUARANTINE
