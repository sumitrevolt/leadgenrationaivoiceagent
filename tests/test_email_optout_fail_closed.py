"""The EMAIL opt-out gate must fail CLOSED — an outage is not consent.

WHY THIS TEST EXISTS
====================
`app/platform/auto_outreach.py` gates every cold email on the opt-out
(suppression) store. It previously returned `set()` / `False` when the store
raised — i.e. it failed OPEN, so a suppression-store outage would have converted
an opted-out recipient into a sendable one. The WhatsApp path was already
fail-CLOSED; the email path was not, which is a DPDP / TCCCPR regression.

The fix introduced a module-level sentinel `_UNREADABLE = object()`:
  * `_suppressed_email_set()` returns `_UNREADABLE` on exception, and
  * `_is_suppressed_email(addr, suppressed=None)` returns `True` when
    `suppressed is _UNREADABLE`, and `True` again if the live lookup raises.

This file pins all four behaviours. The suppression store is monkeypatched — the
real ledger is never touched. THESE TESTS ARE A COMPLIANCE GATE. If any fail, do
NOT "fix" them by loosening an assertion.
"""

from __future__ import annotations

import pytest

from app.platform import auto_outreach as ao
from app.platform import email_unsub


# ------------------------------------------------------- (a) healthy store


def test_healthy_store_reads_and_filters(monkeypatch) -> None:
    monkeypatch.setattr(
        email_unsub, "suppressed_emails", lambda: {"blocked@example.com"}
    )
    s = ao._suppressed_email_set()
    assert s is not ao._UNREADABLE
    assert s == {"blocked@example.com"}
    assert ao._is_suppressed_email("ok@example.com", s) is False
    assert ao._is_suppressed_email("blocked@example.com", s) is True


def test_suppressed_email_set_normalizes_case_and_whitespace(monkeypatch) -> None:
    monkeypatch.setattr(
        email_unsub, "suppressed_emails", lambda: {"blocked@example.com"}
    )
    s = ao._suppressed_email_set()
    assert ao._is_suppressed_email("  BLOCKED@Example.com ", s) is True


# --------------------------------------------- (b) unreadable-store sentinel


def test_suppressed_email_set_returns_sentinel_on_error(monkeypatch) -> None:
    def _boom():
        raise RuntimeError("suppression store down")

    monkeypatch.setattr(email_unsub, "suppressed_emails", _boom)
    assert ao._suppressed_email_set() is ao._UNREADABLE


def test_unreadable_sentinel_blocks_every_recipient() -> None:
    assert ao._is_suppressed_email("anyone@example.com", ao._UNREADABLE) is True
    assert ao._is_suppressed_email("other@example.com", ao._UNREADABLE) is True


# ------------------------------------------- (c) live lookup raising -> True


def test_live_lookup_raising_blocks(monkeypatch) -> None:
    def _boom(_email):
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(email_unsub, "is_suppressed", _boom)
    assert ao._is_suppressed_email("anyone@example.com") is True


# ------------------------------------------------- (d) empty / None address


def test_empty_or_none_address_is_not_suppressed() -> None:
    assert ao._is_suppressed_email("") is False
    assert ao._is_suppressed_email(None) is False
    assert ao._is_suppressed_email("   ") is False


def test_empty_address_short_circuits_even_when_unreadable() -> None:
    """An absent address is not a sendable recipient, so it is not 'suppressed';
    this must not depend on the store being readable."""
    assert ao._is_suppressed_email("", ao._UNREADABLE) is False


# ------------------------------------ call sites: default-arg path still works


def test_default_arg_path_consults_live_store(monkeypatch) -> None:
    """The default-arg path (`suppressed=None`) must still work — the sentinel must
    not break callers that pass no pre-loaded set."""
    monkeypatch.setattr(
        email_unsub, "is_suppressed", lambda e: e == "optedout@example.com"
    )
    assert ao._is_suppressed_email("fresh@example.com") is False
    assert ao._is_suppressed_email("optedout@example.com") is True


def test_sentinel_passed_as_second_arg_blocks(monkeypatch) -> None:
    """The real call sites pass a pre-loaded set as the 2nd arg; when that set is
    the `_UNREADABLE` sentinel they must block."""
    monkeypatch.setattr(
        email_unsub, "suppressed_emails", lambda: (_ for _ in ()).throw(RuntimeError("down"))
    )
    preloaded = ao._suppressed_email_set()
    assert ao._is_suppressed_email("prospect@example.com", preloaded) is True
