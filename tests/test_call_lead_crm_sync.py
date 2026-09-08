"""Call -> lead CRM bucket sync (post_call_hooks.sync_lead_after_call).

Guards the invariants that make this safe to switch on:
  * INERT by default
  * a bot/IVR call is NEVER given a terminal bucket
  * DND comes from the consent ledger, never from LLM output
  * a replayed status callback does not re-apply a transition
"""

from __future__ import annotations

import asyncio

import pytest

from app.telephony import post_call_hooks as pch


# ── flag ────────────────────────────────────────────────────────────────────
def test_crm_sync_is_inert_by_default(monkeypatch):
    monkeypatch.delenv("CALL_LEAD_CRM_SYNC", raising=False)
    assert pch.crm_sync_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "YES", "on"])
def test_crm_sync_flag_accepts_truthy(monkeypatch, val):
    monkeypatch.setenv("CALL_LEAD_CRM_SYNC", val)
    assert pch.crm_sync_enabled() is True


def test_sync_no_ops_when_flag_off(monkeypatch):
    monkeypatch.delenv("CALL_LEAD_CRM_SYNC", raising=False)
    called: list = []
    res = asyncio.run(pch.sync_lead_after_call(lead_id="L1", phone="+919000000000"))
    assert res["skipped"] == "flag_off"
    assert called == []


def test_sync_no_ops_without_lead_id(monkeypatch):
    monkeypatch.setenv("CALL_LEAD_CRM_SYNC", "1")
    res = asyncio.run(pch.sync_lead_after_call(lead_id="  "))
    assert res["skipped"] == "no_lead_id"


# ── classification ──────────────────────────────────────────────────────────
def _no_suppression(monkeypatch):
    from app.telephony import consent_ledger

    monkeypatch.setattr(consent_ledger, "is_suppressed", lambda _p: False)


def test_bot_suspected_never_gets_a_terminal_bucket(monkeypatch):
    """The 2026-07-05 lesson: an IVR tree must stay retryable."""
    _no_suppression(monkeypatch)
    bucket = pch.niche_outcome_for(
        stream_outcome="completed",
        q={"bot_suspected": True, "qualified": False, "interest_score": 1},
        user_turns=2,
        phone="+919000000000",
    )
    assert bucket == "voicemail"
    assert bucket not in {"not_interested", "dnd", "wrong_number"}


def test_qualified_becomes_important_lead(monkeypatch):
    _no_suppression(monkeypatch)
    assert (
        pch.niche_outcome_for(
            stream_outcome="completed",
            q={"qualified": True, "bot_suspected": False},
            user_turns=6,
            phone="+919000000000",
        )
        == "qualified"
    )


def test_appointment_becomes_important_lead(monkeypatch):
    _no_suppression(monkeypatch)
    assert (
        pch.niche_outcome_for(
            stream_outcome="completed",
            q={"appointment_requested": True, "bot_suspected": False},
            user_turns=8,
            phone="+919000000000",
        )
        == "qualified"
    )


def test_real_rejection_becomes_not_interested(monkeypatch):
    _no_suppression(monkeypatch)
    assert (
        pch.niche_outcome_for(
            stream_outcome="completed",
            q={"qualified": False, "bot_suspected": False},
            user_turns=5,
            phone="+919000000000",
        )
        == "not_interested"
    )


def test_no_answer_is_retryable(monkeypatch):
    _no_suppression(monkeypatch)
    assert (
        pch.niche_outcome_for(
            stream_outcome="no_answer", q=None, user_turns=0, phone="+919000000000"
        )
        == "voicemail"
    )


def test_unknown_classification_falls_back_to_retryable(monkeypatch):
    """_map_call_outcome returning None must not strand the lead terminally."""
    _no_suppression(monkeypatch)
    monkeypatch.setattr(pch, "_map_call_outcome", lambda *a, **k: None)
    assert (
        pch.niche_outcome_for(stream_outcome="completed", q={}, user_turns=3, phone="+919000000000")
        == "voicemail"
    )


# ── DND ─────────────────────────────────────────────────────────────────────
def test_dnd_comes_from_consent_ledger_and_wins(monkeypatch):
    from app.telephony import consent_ledger

    monkeypatch.setattr(consent_ledger, "is_suppressed", lambda _p: True)
    # even a "qualified" call must yield dnd once the lead opted out
    assert (
        pch.niche_outcome_for(
            stream_outcome="completed",
            q={"qualified": True},
            user_turns=9,
            phone="+919000000000",
        )
        == "dnd"
    )


def test_dnd_is_never_inferred_from_llm_output(monkeypatch):
    """No qualification field may manufacture a DND bucket."""
    _no_suppression(monkeypatch)
    for q in (
        {"opt_out": True},
        {"detected_intent": "opt_out"},
        {"summary": "customer said do not call me again, add to DND"},
    ):
        assert (
            pch.niche_outcome_for(
                stream_outcome="completed", q=q, user_turns=4, phone="+919000000000"
            )
            != "dnd"
        )


def test_suppression_lookup_failure_does_not_raise(monkeypatch):
    from app.telephony import consent_ledger

    def _boom(_p):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(consent_ledger, "is_suppressed", _boom)
    # falls through to the normal classifier rather than propagating
    assert (
        pch.niche_outcome_for(
            stream_outcome="no_answer", q=None, user_turns=0, phone="+919000000000"
        )
        == "voicemail"
    )


# ── delegation + resilience ─────────────────────────────────────────────────
def test_sync_delegates_to_update_after_call(monkeypatch):
    monkeypatch.setenv("CALL_LEAD_CRM_SYNC", "1")
    _no_suppression(monkeypatch)
    seen: dict = {}

    async def _fake(**kwargs):
        seen.update(kwargs)
        return {"ok": True, "status": "qualified", "lead_id": kwargs["lead_id"]}

    import app.platform.niche_database as nd

    monkeypatch.setattr(nd, "update_after_call", _fake)

    res = asyncio.run(
        pch.sync_lead_after_call(
            lead_id="L42",
            phone="+919000000000",
            outcome="completed",
            q={"qualified": True, "summary": "wants a demo"},
            user_turns=7,
        )
    )
    assert res["ok"] is True
    assert res["bucket"] == "qualified"
    assert seen["lead_id"] == "L42"
    assert seen["outcome"] == "qualified"
    assert seen["notes"] == "wants a demo"


def test_sync_never_raises_when_update_blows_up(monkeypatch):
    monkeypatch.setenv("CALL_LEAD_CRM_SYNC", "1")
    _no_suppression(monkeypatch)

    async def _boom(**kwargs):
        raise RuntimeError("db gone")

    import app.platform.niche_database as nd

    monkeypatch.setattr(nd, "update_after_call", _boom)

    res = asyncio.run(pch.sync_lead_after_call(lead_id="L1", phone="+919000000000", user_turns=1))
    assert res["ok"] is False
    assert "error" in res


# ── idempotency contract ────────────────────────────────────────────────────
def test_persist_call_log_skips_sync_on_duplicate(monkeypatch):
    """A replayed status callback must not re-apply a status transition.

    _insert_sync returns "" for a duplicate call_sid; persist_call_log must
    then skip the CRM sync entirely.
    """
    monkeypatch.setenv("CALL_LEAD_CRM_SYNC", "1")
    calls: list = []

    async def _spy(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(pch, "sync_lead_after_call", _spy)
    monkeypatch.setattr(pch.asyncio, "to_thread", _mk_to_thread(""))

    asyncio.run(
        pch.persist_call_log(call_id="c1", provider="phone", phone="+919000000000", lead_id="L1")
    )
    assert calls == []


def test_persist_call_log_syncs_on_fresh_insert(monkeypatch):
    monkeypatch.setenv("CALL_LEAD_CRM_SYNC", "1")
    calls: list = []

    async def _spy(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(pch, "sync_lead_after_call", _spy)
    monkeypatch.setattr(pch.asyncio, "to_thread", _mk_to_thread("L1"))

    asyncio.run(
        pch.persist_call_log(call_id="c2", provider="phone", phone="+919000000000", lead_id="L1")
    )
    assert len(calls) == 1
    assert calls[0]["lead_id"] == "L1"


def test_persist_call_log_skips_sync_when_insert_fails(monkeypatch):
    monkeypatch.setenv("CALL_LEAD_CRM_SYNC", "1")
    calls: list = []

    async def _spy(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    async def _raise(fn, *a, **k):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(pch, "sync_lead_after_call", _spy)
    monkeypatch.setattr(pch.asyncio, "to_thread", _raise)

    asyncio.run(
        pch.persist_call_log(call_id="c3", provider="phone", phone="+919000000000", lead_id="L1")
    )
    assert calls == []


def _mk_to_thread(ret):
    async def _to_thread(fn, *a, **k):
        return ret

    return _to_thread
