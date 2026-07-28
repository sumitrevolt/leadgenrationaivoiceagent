"""Unified suppression: one canonical authority enforced by every send path.

Root cause this pins: `email_unsub.suppress()` had exactly ONE caller in all of
`app/` — the one-click HTTP endpoint. Every outreach email says "reply REMOVE",
but a REMOVE reply only marked the prospect row dead; the address stayed mailable
from any other row and WhatsApp was never touched. The advertised opt-out did not
work at the list level.

Scope semantics under test:
  EMAIL_ADDRESS  -> blocks that mailbox, must NOT silence a valid phone
  CHANNEL_CONTACT-> blocks one channel
  ALL_OUTREACH   -> blocks every automated channel (explicit opt-out)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.platform import email_unsub


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Never touch the real data/email_suppression.jsonl.

    conftest's autouse isolation covers billing only, so without this a test run
    on the VPS would write into the live suppression ledger.
    """
    store = tmp_path / "email_suppression.jsonl"
    monkeypatch.setattr(email_unsub, "_store_path", lambda: store)
    return store


# ---------------------------------------------------------------- normalizers
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Foo@Example.COM ", "foo@example.com"),
        ("foo@example.com", "foo@example.com"),
        ("", ""),
    ],
)
def test_normalize_email(raw: str, expected: str) -> None:
    assert email_unsub.normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+91 98765 43210", "9876543210"),
        ("919876543210", "9876543210"),
        ("9876543210", "9876543210"),
    ],
)
def test_normalize_phone_variants_collapse(raw: str, expected: str) -> None:
    """A suppression that missed on formatting would keep messaging someone."""
    assert email_unsub.normalize_phone(raw) == expected


# ------------------------------------------------------------- opt-out scopes
def test_remove_reply_creates_durable_all_outreach_suppression() -> None:
    assert email_unsub.suppress(
        "a@b.com", reason="reply_unsubscribe", scope=email_unsub.SCOPE_ALL_OUTREACH
    )
    assert email_unsub.is_suppressed("a@b.com") is True


def test_all_outreach_blocks_whatsapp_by_prospect_identity() -> None:
    """Cross-channel invariant: opt-out by email must stop WhatsApp too."""
    email_unsub.suppress(
        "a@b.com",
        reason="reply_unsubscribe",
        scope=email_unsub.SCOPE_ALL_OUTREACH,
        prospect_id="p1",
    )
    assert email_unsub.is_phone_suppressed(prospect_id="p1") is True
    assert (
        email_unsub.is_contact_suppressed(phone="9876543210", prospect_id="p1", channel="whatsapp")
        is True
    )


def test_all_outreach_blocks_whatsapp_by_phone() -> None:
    email_unsub.suppress(
        "", reason="stop", scope=email_unsub.SCOPE_ALL_OUTREACH, phone="+91 98765 43210"
    )
    assert email_unsub.is_phone_suppressed(phone="919876543210") is True


# ------------------------------------------- hard bounce must NOT go global
def test_hard_bounce_suppresses_email_only() -> None:
    """A dead mailbox says nothing about the phone — it must stay reachable."""
    email_unsub.suppress(
        "dead@b.com",
        reason="hard_bounce",
        scope=email_unsub.SCOPE_EMAIL_ADDRESS,
        prospect_id="p2",
        phone="9876543211",
    )
    assert email_unsub.is_suppressed("dead@b.com") is True
    assert email_unsub.is_phone_suppressed(phone="9876543211") is False
    assert email_unsub.is_phone_suppressed(prospect_id="p2") is False
    assert (
        email_unsub.is_contact_suppressed(phone="9876543211", prospect_id="p2", channel="whatsapp")
        is False
    )


def test_channel_contact_scope_blocks_only_that_channel() -> None:
    email_unsub.suppress(
        "c@b.com",
        reason="wa_optout",
        scope=email_unsub.SCOPE_CHANNEL_CONTACT,
        channel="whatsapp",
        phone="9876543212",
    )
    assert email_unsub.is_phone_suppressed(phone="9876543212") is True
    assert email_unsub.is_suppressed("c@b.com") is False


# -------------------------------------------------------------- idempotency
def test_duplicate_event_id_is_idempotent(isolated_store: Path) -> None:
    """Webhook retry / reply reprocessing must not append twice."""
    for _ in range(3):
        email_unsub.suppress(
            "dup@b.com",
            reason="complaint",
            scope=email_unsub.SCOPE_EMAIL_ADDRESS,
            event_id="evt-123",
        )
    lines = [ln for ln in isolated_store.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected 1 row, got {len(lines)}"
    assert email_unsub.is_suppressed("dup@b.com") is True


def test_distinct_event_ids_both_recorded(isolated_store: Path) -> None:
    email_unsub.suppress("x@b.com", scope=email_unsub.SCOPE_EMAIL_ADDRESS, event_id="e1")
    email_unsub.suppress("y@b.com", scope=email_unsub.SCOPE_EMAIL_ADDRESS, event_id="e2")
    lines = [ln for ln in isolated_store.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


# ------------------------------------------------------- fail-closed / legacy
def test_unknown_scope_fails_closed_to_all_outreach() -> None:
    """A malformed scope must not write a row nothing will ever match."""
    email_unsub.suppress("weird@b.com", reason="?", scope="not-a-real-scope", prospect_id="p9")
    assert email_unsub.is_suppressed("weird@b.com") is True
    assert email_unsub.is_phone_suppressed(prospect_id="p9") is True


def test_legacy_rows_without_scope_still_block_email(isolated_store: Path) -> None:
    """Pre-existing ledger rows have no `scope` key — they must keep working."""
    isolated_store.parent.mkdir(parents=True, exist_ok=True)
    isolated_store.write_text(
        '{"email": "legacy@b.com", "reason": "one_click", "ts": 1}\n', encoding="utf-8"
    )
    assert email_unsub.is_suppressed("legacy@b.com") is True
    # legacy == email-address scope, so the phone stays reachable
    assert email_unsub.is_phone_suppressed(phone="9999999999") is False


def test_blank_identity_writes_nothing(isolated_store: Path) -> None:
    assert email_unsub.suppress("", scope=email_unsub.SCOPE_ALL_OUTREACH) is False
    assert not isolated_store.exists() or isolated_store.read_text(encoding="utf-8").strip() == ""


def test_case_and_format_mismatch_still_suppressed() -> None:
    """Send path used to .strip() only while lookup lowercased."""
    email_unsub.suppress("MiXeD@Case.COM ", scope=email_unsub.SCOPE_EMAIL_ADDRESS)
    assert email_unsub.is_suppressed("mixed@case.com") is True
    assert email_unsub.is_suppressed(" MIXED@CASE.com ") is True


# ================================================================= eligibility
from app.platform.sales_autopilot import eligibility as _elig  # noqa: E402
from app.platform.sales_autopilot import send as _send  # noqa: E402


class _LivePolicy:
    enabled = True
    dry_run = False

    def channel_enabled(self, channel: str) -> bool:
        return True

    def kill(self, _stage: str) -> bool:
        return False

    def canary_batch(self) -> int:
        return 1

    def get(self, key: str, default: Any = None) -> Any:
        return {
            "provider_timeout_s": 20,
            "stop_on_reply": False,
            "stop_on_payment": False,
            "channels": ["email", "whatsapp"],
            "ist_hours": {"start": 0, "end": 24},
            "caps": {"daily_new_outreach": 99, "daily_followups": 99},
        }.get(key, default)

    def max_followups(self) -> int:
        return 3


def _prospect(**over: Any) -> dict[str, Any]:
    base = {
        "id": "p-sup-1",
        "phone": "9876543210",
        "email": "opt@out.com",
        "status": "new",
        "consent_basis": "legitimate_interest",
        "business_name": "Suppression Test Biz",
    }
    base.update(over)
    return base


def test_opt_out_blocks_sales_autopilot_email(monkeypatch) -> None:
    email_unsub.suppress("opt@out.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-sup-1")
    monkeypatch.setattr(_elig._store, "get_prospect", lambda _p: _prospect())
    out = _elig.evaluate(_prospect(), channel="email", step=_elig.STEP_INITIAL, pol=_LivePolicy())
    assert out["decision"] == _elig.INELIGIBLE
    assert "suppressed_canonical" in out["reason_codes"]


def test_opt_out_blocks_sales_autopilot_whatsapp(monkeypatch) -> None:
    # Pin the PRE-EXISTING WhatsApp campaign check to False. It reads the repo's
    # data/wa_suppression.jsonl, so leaving it live made this test depend on
    # checkout state: it passed locally and FAILED in CI, where that file already
    # suppressed the number and returned "suppressed" before the canonical check
    # ever ran. Forcing it False is what makes this test prove the canonical
    # authority fires, rather than the old one masking it.
    monkeypatch.setattr(_elig, "_is_suppressed", lambda _c: False)
    email_unsub.suppress("opt@out.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-sup-1")
    monkeypatch.setattr(_elig._store, "get_prospect", lambda _p: _prospect())
    out = _elig.evaluate(
        _prospect(), channel="whatsapp", step=_elig.STEP_INITIAL, pol=_LivePolicy()
    )
    assert out["decision"] == _elig.INELIGIBLE
    assert "suppressed_canonical" in out["reason_codes"]


def test_hard_bounce_does_not_block_whatsapp_eligibility(monkeypatch) -> None:
    """The anti-over-block test: an email bounce must leave WhatsApp allowed."""
    email_unsub.suppress(
        "opt@out.com",
        scope=email_unsub.SCOPE_EMAIL_ADDRESS,
        prospect_id="p-sup-1",
        reason="hard_bounce",
    )
    monkeypatch.setattr(_elig._store, "get_prospect", lambda _p: _prospect())
    monkeypatch.setattr(_elig, "_is_suppressed", lambda _c: False)
    out = _elig.evaluate(
        _prospect(), channel="whatsapp", step=_elig.STEP_INITIAL, pol=_LivePolicy()
    )
    assert out["decision"] == _elig.ELIGIBLE, out


def test_unsuppressed_contact_remains_eligible(monkeypatch) -> None:
    """Anti-regression: a fix that blocked everything would pass the tests above."""
    monkeypatch.setattr(_elig._store, "get_prospect", lambda _p: _prospect())
    monkeypatch.setattr(_elig, "_is_suppressed", lambda _c: False)
    out = _elig.evaluate(
        _prospect(), channel="whatsapp", step=_elig.STEP_INITIAL, pol=_LivePolicy()
    )
    assert out["decision"] == _elig.ELIGIBLE, out


# ======================================== pre-provider recheck (defense in depth)
class ProviderCalled(AssertionError):
    pass


def _arm_send(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Drive send() past eligibility/build/validate to the provider boundary."""
    calls = {"n": 0}

    async def _bomb(*a: Any, **k: Any) -> dict[str, Any]:
        calls["n"] += 1
        raise ProviderCalled("provider invoked after suppression")

    monkeypatch.setattr(_send, "_provider_send_whatsapp", _bomb)
    monkeypatch.setattr(_send._elig, "evaluate", lambda *a, **k: {"decision": _send._elig.ELIGIBLE})
    monkeypatch.setattr(
        _send._messages,
        "build",
        lambda *a, **k: {
            "template_family": "initial",
            "template_version": "v1",
            "content_hash": "cafe",
            "body": "hi",
        },
    )
    monkeypatch.setattr(
        _send._safety,
        "validate",
        lambda _e: {"status": _send._safety.AUTO_APPROVED, "reasons": []},
    )
    monkeypatch.setattr(_send._store, "attempt_exists", lambda _k: False)
    monkeypatch.setattr(_send._store, "record_attempt", lambda _r: None)
    monkeypatch.setattr(_send._store, "update_attempt_status", lambda *a, **k: None)
    monkeypatch.setattr(_send, "_advance_prospect", lambda *a, **k: None)
    return calls


def test_suppression_after_scheduling_blocks_at_provider_boundary(monkeypatch) -> None:
    """THE defense-in-depth test.

    Eligibility is stubbed ELIGIBLE (as if it passed at scheduling time), then
    suppression lands. The send must still not reach the provider. This proves
    the recheck runs at the pre-provider boundary, not only at scheduling.
    """
    calls = _arm_send(monkeypatch)
    email_unsub.suppress("opt@out.com", scope=email_unsub.SCOPE_ALL_OUTREACH, prospect_id="p-sup-1")

    res = asyncio.run(
        _send.send(
            "p-sup-1",
            channel="whatsapp",
            pol=_LivePolicy(),
            prospect=_prospect(),
        )
    )

    assert calls["n"] == 0, "provider was called despite suppression"
    assert res["outcome"] == _send.SKIPPED
    assert res["reason"] == "suppressed_pre_provider"


def test_unsuppressed_send_still_reaches_provider(monkeypatch) -> None:
    """Anti-regression for the recheck: normal sends must still go out."""
    seen: dict[str, Any] = {}

    async def _capture(contact: str, body: str, timeout_s: float) -> dict[str, Any]:
        seen["contact"] = contact
        return {"sent": True, "mode": "live"}

    _arm_send(monkeypatch)
    monkeypatch.setattr(_send, "_provider_send_whatsapp", _capture)

    res = asyncio.run(
        _send.send(
            "p-sup-1",
            channel="whatsapp",
            pol=_LivePolicy(),
            prospect=_prospect(),
        )
    )
    assert seen.get("contact") == "9876543210"
    assert res["outcome"] == _send.SENT


def test_pre_provider_check_fails_closed(monkeypatch) -> None:
    """If the ledger cannot be read, skip the send rather than risk it."""
    calls = _arm_send(monkeypatch)

    def _boom(**_k: Any) -> bool:
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(email_unsub, "is_contact_suppressed", _boom)

    res = asyncio.run(
        _send.send(
            "p-sup-1",
            channel="whatsapp",
            pol=_LivePolicy(),
            prospect=_prospect(),
        )
    )
    assert calls["n"] == 0
    assert res["reason"] == "suppressed_pre_provider"


# ============================================================ one-click intact
def test_one_click_unsubscribe_still_works() -> None:
    """Existing endpoint semantics must be unchanged (default scope = email)."""
    tok = email_unsub.make_token("click@b.com")
    assert email_unsub.verify_token(tok) == "click@b.com"
    assert email_unsub.suppress("click@b.com", "one_click") is True
    assert email_unsub.is_suppressed("click@b.com") is True
    # default scope stays address-level -> phone untouched
    assert email_unsub.is_phone_suppressed(phone="9876543210") is False


def test_suppressed_emails_bulk_filter_includes_new_rows() -> None:
    """auto_outreach bulk-preloads this set; new scoped rows must appear in it."""
    email_unsub.suppress("bulk@b.com", scope=email_unsub.SCOPE_ALL_OUTREACH)
    assert "bulk@b.com" in email_unsub.suppressed_emails()
