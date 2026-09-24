"""WORKBUDDY-EMAIL-002 — TypeSafe reply-triage wiring regression tests.

Verifies the opt-in, fail-safe TypeSafe integration added to
``app/platform/reply_agent.py``:

* ``_typesafe_triage_evidence`` — reuses the canonical
  ``typesafe_services.TypeSafeReplyTriage``; INERT/unavailable degrades
  gracefully (no call, no network, LLM verdict stands); a genuine LLM-vs-TypeSafe
  conflict demotes a hot call to review instead of inventing intent.
* ``create_reply_followup_task`` — idempotent canonical ``task_ledger`` follow-up
  task (no second task DB), TypeSafe evidence persisted, flag-off is a no-op.
* ``_typesafe_content_gate`` — reuses the canonical ``typesafe_services.
  TypeSafeContentQA`` as an opt-in pre-send verdict; INERT fails open (never
  blocks the bounded auto-send just because the paid verifier is down).

All TypeSafe calls are faked via the ``typesafe_services`` factory monkeypatch,
so these tests are hermetic and make no network call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.platform import reply_agent, typesafe_services


# --------------------------------------------------------------------------- #
# Fakes for the canonical services (no network)
# --------------------------------------------------------------------------- #
@dataclass
class _FakeTriage:
    intent: str
    is_hot: bool
    sentiment: str
    urgency: str
    suggested_action: str
    metadata: dict[str, Any] = field(default_factory=dict)


class _FakeTriageService:
    """Stand-in for TypeSafeReplyTriage with a controllable enabled flag."""

    def __init__(self, enabled: bool, result: _FakeTriage | None):
        self.enabled = enabled
        self.result = result
        self.client = _StubClient(enabled)

    def triage_reply(self, _text, _ctx=None):
        assert self.result is not None
        return self.result


class _StubClient:
    def __init__(self, enabled: bool):
        self.enabled = enabled


def _triage_svc(intent, is_hot=False, enabled=True, latency=0.5, model="jev-1.13.0"):
    return _FakeTriageService(
        enabled,
        _FakeTriage(
            intent=intent,
            is_hot=is_hot,
            sentiment="positive" if is_hot else "neutral",
            urgency="same_day" if is_hot else "routine",
            suggested_action="schedule_call" if is_hot else "answer_query",
            metadata={"model": model, "latency_sec": latency},
        )
        if enabled
        else None,
    )


class _FakeContentQASvc:
    def __init__(
        self,
        enabled: bool,
        approved: bool,
        tone="professional",
        reasons=(),
        success=True,
        has_answer=True,
    ):
        self.enabled = enabled
        self._approved = approved
        self._tone = tone
        self._reasons = list(reasons)
        self._success = success
        self._has_answer = has_answer
        self.client = _StubClient(enabled)

    def audit_outbound_message(self, subject, body, channel="email", recipient_context=None):
        return _FakeContentVerdict(
            self._approved, self._tone, self._reasons, self._success, self._has_answer
        )


class _FakeContentVerdict:
    def __init__(self, approved, tone, reasons, success=True, has_answer=True):
        self.approved = approved
        self.persuasion_score = "strong" if approved else "weak"
        self.tone = tone
        self.compliance_violation = (not approved) and (tone == "aggressive")
        self.is_spammy = not approved
        self.reasons = reasons
        # Mirror the real ContentQAResult.metadata contract (success + has_answer),
        # which the gate's `needs_review`/`state` decision depends on.
        self.metadata = {
            "model": "jev-1.13.0",
            "latency_sec": 0.6,
            "success": bool(success),
            "has_answer": bool(has_answer),
            "attempts": 1,
        }


def _content_svc(
    approved=True, enabled=True, tone="professional", reasons=(), success=True, has_answer=True
):
    return _FakeContentQASvc(enabled, approved, tone, reasons, success, has_answer)


@pytest.fixture(autouse=True)
def _isolate_flags(monkeypatch):
    """Ensure the new opt-in flags are OFF unless a test turns them on."""
    for name in (
        "REPLY_AGENT_TYPESAFE",
        "REPLY_AGENT_TYPESAFE_CONTENT",
        "REPLY_AGENT_FOLLOWUP_TASK",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


# --------------------------------------------------------------------------- #
# _typesafe_triage_evidence
# --------------------------------------------------------------------------- #
def test_triage_evidence_inactive_when_flag_off(monkeypatch):
    # Flag off (autouse) -> no TypeSafe call, even if the service would be active.
    monkeypatch.setattr(
        typesafe_services, "get_typesafe_reply_triage", lambda: _triage_svc("demo_request", True)
    )
    ev = reply_agent._typesafe_triage_evidence("s", "b", "interested", None)
    assert ev == {"active": False}


def test_triage_evidence_inert_records_state(monkeypatch):
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_reply_triage",
        lambda: _triage_svc("demo_request", enabled=False),
    )
    ev = reply_agent._typesafe_triage_evidence("s", "b", "interested", None)
    assert ev == {"active": False, "reason": "inert"}


def test_triage_evidence_active_records_invocation(monkeypatch):
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_reply_triage",
        lambda: _triage_svc("demo_request", is_hot=True, latency=1.06, model="jev-1.13.0"),
    )
    ev = reply_agent._typesafe_triage_evidence(
        "Re: audit",
        "demo this week please",
        "interested",
        {"business_name": "Jiya", "niche": "salon"},
    )
    assert ev["active"] is True
    assert ev["intent"] == "demo_request"
    assert ev["is_hot"] is True
    assert ev["suggested_action"] == "schedule_call"
    assert ev["model"] == "jev-1.13.0"
    assert ev["latency_sec"] == 1.06
    # LLM 'interested' agrees with a hot demo request -> no conflict.
    assert ev["conflict"] is False


def test_triage_evidence_conflict_demotes_to_review(monkeypatch):
    # LLM said 'interested' (hot) but TypeSafe is a confident unsubscribe.
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_reply_triage",
        lambda: _triage_svc("unsubscribe", is_hot=False),
    )
    ev = reply_agent._typesafe_triage_evidence("s", "no thanks, stop emailing", "interested", None)
    assert ev["active"] is True
    assert ev["conflict"] is True
    assert ev["mapped_intent"] == "unsubscribe"


def test_triage_evidence_negative_body_conflict_hot_lead(monkeypatch):
    # A 'question' LLM label vs a TypeSafe not_interested decline = conflict.
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_reply_triage",
        lambda: _triage_svc("not_interested", is_hot=False),
    )
    ev = reply_agent._typesafe_triage_evidence("s", "not interested", "question", None)
    assert ev["conflict"] is True


# --------------------------------------------------------------------------- #
# create_reply_followup_task  (canonical WORKER ledger: orchestrator_ledger.db)
# --------------------------------------------------------------------------- #
def _temp_orchestrator(tmp_path):
    """Point the durable task store at a temp DB so the test never touches the
    real `data/orchestrator_ledger.db`."""
    from app.platform.automation_orchestrator import (
        AutomationOrchestrator,
        DurableTaskStore,
    )

    db = str(tmp_path / "orchestrator_ledger.db")
    store = DurableTaskStore(db_path=db, ledger_file=str(tmp_path / "orchestrator_ledger.json"))
    return AutomationOrchestrator(store=store)


def test_followup_task_noop_when_flag_off():
    # autouse fixture leaves the flag off -> no task DB access at all.
    out = reply_agent.create_reply_followup_task(
        {"business_name": "Jiya Makeover", "email": "j@x.in"}, "interested", {"active": True}
    )
    assert out["created"] is False
    assert out.get("reason") == "flag_off"


def test_followup_task_targets_orchestrator_ledger(tmp_path, monkeypatch):
    # Boss point 4: the follow-up task must land in the canonical worker-execution
    # ledger (data/orchestrator_ledger.db), with a durable id, owner + agent and
    # TypeSafe evidence — NOT the admin Kanban (data/admin_tasks.db).
    orch = _temp_orchestrator(tmp_path)
    monkeypatch.setenv("REPLY_AGENT_FOLLOWUP_TASK", "1")
    prospect = {"business_name": "Jiya Makeover", "email": "j@x.in"}
    ts_ev = {"active": True, "intent": "demo_request", "is_hot": True, "model": "jev-1.13.0"}

    first = reply_agent.create_reply_followup_task(
        prospect,
        "interested",
        ts_ev,
        idempotency_key="reply_followup:j@x.in::<thread>",
        orchestrator=orch,
    )
    assert first["created"] is True
    assert first["task_id"] is not None
    assert first["owner_bot"] == "sales"
    assert first["assigned_agent"] == "rohan"

    # Durable: the record is retrievable from the orchestrator store.
    record = orch.store.get(first["task_id"])
    assert record is not None
    assert record.input_payload["typesafe"]["intent"] == "demo_request"
    assert record.input_payload["business"] == "Jiya Makeover"

    # Idempotent: re-processing the same thread returns the SAME task, no new row.
    second = reply_agent.create_reply_followup_task(
        prospect,
        "interested",
        ts_ev,
        idempotency_key="reply_followup:j@x.in::<thread>",
        orchestrator=orch,
    )
    assert second["created"] is False
    assert second.get("reason") == "duplicate"
    assert second["task_id"] == first["task_id"]


def test_followup_key_stable_from_thread_identity():
    """Boss #5: the default idempotency key is derived from stable delivery/thread
    identity, NOT a per-process Python ``hash()``. The same message yields the same
    key every time; two DIFFERENT threads from the same sender stay distinct; a
    missing Message-ID falls back to a DISTINCT durable thread-root (never a shared
    ``'none'`` constant)."""
    # Same sender + same Message-ID -> identical key, stable across calls.
    k1 = reply_agent._followup_task_key("j@x.in", "<abc@mail>", "<r0> <abc@mail>")
    k2 = reply_agent._followup_task_key("j@x.in", "<abc@mail>", "<r0> <abc@mail>")
    assert k1 == k2
    assert k1.startswith("reply_followup:")
    # Sender is lower-cased into the identity.
    assert k1 == reply_agent._followup_task_key("J@X.IN", "<abc@mail>")

    # Distinct threads (no Message-ID, only References) stay DISTINCT — no collapse
    # to a shared 'none' constant.
    a = reply_agent._followup_task_key("j@x.in", "", "<r-a>")
    b = reply_agent._followup_task_key("j@x.in", "", "<r-b>")
    assert a != b

    # Missing Message-ID -> durable thread-root fallback; present -> Message-ID form.
    assert a.startswith("reply_followup:")
    assert k1 != a  # different identity material

    # Deterministic: not salted per-process (Python hash() would differ by seed).
    assert reply_agent._followup_task_key("j@x.in", "<abc@mail>") == k1
    assert reply_agent._followup_task_key("", "<x>") == "reply_followup:<nosender>"


def test_followup_key_missing_message_id_distinct_durable(tmp_path, monkeypatch):
    """Two threads from the same sender WITHOUT a Message-ID must NOT collapse to
    one shared key; each gets a distinct durable key via the thread-root fallback."""
    monkeypatch.setenv("REPLY_AGENT_FOLLOWUP_TASK", "1")
    orch = _temp_orchestrator(tmp_path)
    prospect = {"business_name": "Jiya Makeover", "email": "j@x.in"}
    ts_ev = {"active": True, "intent": "demo_request", "is_hot": True, "model": "jev-1.13.0"}

    t1 = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, message_id="", references="<r-1>", orchestrator=orch
    )
    t2 = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, message_id="", references="<r-2>", orchestrator=orch
    )
    assert t1["created"] is True and t2["created"] is True
    assert t1["task_id"] != t2["task_id"]
    assert t1["idempotency_key"] != t2["idempotency_key"]

    # A retry of thread 1 dedups; a retry of thread 2 dedups independently.
    t1b = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, message_id="", references="<r-1>", orchestrator=orch
    )
    t2b = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, message_id="", references="<r-2>", orchestrator=orch
    )
    assert t1b["created"] is False and t1b["reason"] == "duplicate"
    assert t1b["task_id"] == t1["task_id"]
    assert t2b["created"] is False and t2b["reason"] == "duplicate"
    assert t2b["task_id"] == t2["task_id"]


def test_followup_key_dedups_across_restart(tmp_path, monkeypatch):
    """Cross-process/restart regression: simulate a RESTART by building a fresh
    orchestrator (fresh DurableTaskStore) over the SAME ledger DB, then re-submit
    with the identically-derived key. The second (new-process) submission must be
    a duplicate of the first process's task — proving the key is stable across a
    process boundary, which a per-process Python ``hash()`` would break."""
    monkeypatch.setenv("REPLY_AGENT_FOLLOWUP_TASK", "1")
    db = str(tmp_path / "orchestrator_ledger.db")
    ledger = str(tmp_path / "orchestrator_ledger.json")

    # ---- "process 1": build orchestrator, submit, capture the task + key. ----
    from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore

    orch1 = AutomationOrchestrator(store=DurableTaskStore(db_path=db, ledger_file=ledger))
    prospect = {"business_name": "Jiya Makeover", "email": "j@x.in"}
    ts_ev = {"active": True, "intent": "demo_request", "is_hot": True, "model": "jev-1.13.0"}
    p1 = reply_agent.create_reply_followup_task(
        prospect,
        "interested",
        ts_ev,
        message_id="<abc@mail>",
        references="<r0>",
        orchestrator=orch1,
    )
    assert p1["created"] is True and p1["task_id"]
    key = p1["idempotency_key"]

    # ---- "process 2": a brand-new orchestrator instance over the SAME db. ----
    orch2 = AutomationOrchestrator(store=DurableTaskStore(db_path=db, ledger_file=ledger))
    p2 = reply_agent.create_reply_followup_task(
        prospect,
        "interested",
        ts_ev,
        message_id="<abc@mail>",
        references="<r0>",
        orchestrator=orch2,
    )
    # Independently re-deriving the key must land on the SAME task.
    assert p2["created"] is False
    assert p2["reason"] == "duplicate"
    assert p2["task_id"] == p1["task_id"]
    assert p2["idempotency_key"] == key


def test_followup_caller_uses_current_message_identity(tmp_path, monkeypatch):
    """Regression for the stale-variable defect: the triage call site must derive
    the key from the CURRENT message's thread identity, not a sibling variable that
    is only populated later in the loop. Here we call exactly as the caller does —
    passing message_id/references straight from _safe_thread_headers of THIS msg —
    and confirm the resulting key is stable and dedup-safe."""
    import email as email_mod

    monkeypatch.setenv("REPLY_AGENT_FOLLOWUP_TASK", "1")
    orch = _temp_orchestrator(tmp_path)
    raw = (
        b"From: J <j@x.in>\r\nSubject: Re: demo\r\n"
        b"Message-ID: <msg-777@x.in>\r\nReferences: <r0@x.in> <msg-777@x.in>\r\n"
        b"\r\nYes, do a demo this week.\r\n"
    )
    msg = email_mod.message_from_bytes(raw)
    fmid, frefs = reply_agent._safe_thread_headers(msg)
    assert fmid == "<msg-777@x.in>"
    prospect = {"business_name": "Jiya Makeover", "email": "j@x.in"}
    ts_ev = {"active": True, "intent": "demo_request", "is_hot": True}
    out = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, message_id=fmid, references=frefs, orchestrator=orch
    )
    assert out["created"] is True
    assert out["idempotency_key"] == reply_agent._followup_task_key("j@x.in", fmid, frefs)


def test_followup_key_uid_fallback_keeps_distinct_messages(tmp_path, monkeypatch):
    """Boss rev3: when a message has NO Message-ID and NO References, the durable
    IMAP UID distinguishes two distinct messages from the same sender — they must
    NOT collapse into one shared sender-scoped key."""
    monkeypatch.setenv("REPLY_AGENT_FOLLOWUP_TASK", "1")
    orch = _temp_orchestrator(tmp_path)
    prospect = {"business_name": "Jiya Makeover", "email": "j@x.in"}
    ts_ev = {"active": True, "intent": "demo_request", "is_hot": True}

    # Two messages with different UIDs from the same sender, no thread identity:
    m1 = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, uid="1001", orchestrator=orch
    )
    m2 = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, uid="1002", orchestrator=orch
    )
    # Distinct tasks:
    assert m1["created"] is True
    assert m2["created"] is True
    assert m1["task_id"] != m2["task_id"]
    assert m1["idempotency_key"] != m2["idempotency_key"]

    # Same UID is a duplicate (idempotent replay within one process):
    m1_replay = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, uid="1001", orchestrator=orch
    )
    assert m1_replay["created"] is False
    assert m1_replay["reason"] == "duplicate"
    assert m1_replay["task_id"] == m1["task_id"]


def test_followup_key_uid_survives_restart(tmp_path, monkeypatch):
    """Cross-process/restart: a fresh orchestrator over the same ledger DB sees the
    same UID-derived key as a duplicate — proving the UID fallback is stable across
    a restart (the core requirement for dedup of identifier-less replies)."""
    monkeypatch.setenv("REPLY_AGENT_FOLLOWUP_TASK", "1")
    db = str(tmp_path / "orchestrator_ledger.db")
    ledger = str(tmp_path / "orchestrator_ledger.json")
    from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore

    orch1 = AutomationOrchestrator(store=DurableTaskStore(db_path=db, ledger_file=ledger))
    prospect = {"business_name": "Jiya Makeover", "email": "j@x.in"}
    ts_ev = {"active": True, "intent": "demo_request", "is_hot": True}

    p1 = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, uid="1001", orchestrator=orch1
    )
    assert p1["created"] is True

    orch2 = AutomationOrchestrator(store=DurableTaskStore(db_path=db, ledger_file=ledger))
    p2 = reply_agent.create_reply_followup_task(
        prospect, "interested", ts_ev, uid="1001", orchestrator=orch2
    )
    assert p2["created"] is False
    assert p2["reason"] == "duplicate"
    assert p2["task_id"] == p1["task_id"]


def test_followup_no_identity_does_not_mint_task(tmp_path, monkeypatch):
    """When NO Message-ID, NO References, and NO UID are available, the key
    resolves to the explicit <review> marker — the function does NOT create a task
    (preventing silent sender-scoped dedup collapse). It returns the review path
    so the caller can surface it."""
    monkeypatch.setenv("REPLY_AGENT_FOLLOWUP_TASK", "1")
    orch = _temp_orchestrator(tmp_path)
    prospect = {"business_name": "Jiya Makeover", "email": "j@x.in"}
    ts_ev = {"active": True, "intent": "demo_request", "is_hot": True}

    out = reply_agent.create_reply_followup_task(prospect, "interested", ts_ev, orchestrator=orch)
    # No identity at all: no task minted; explicit review marker returned.
    assert out["created"] is False
    assert out.get("reason") == "review:missing_message_identity"
    assert out["task_id"] is None
    assert out["idempotency_key"] == "reply_followup:<review>"

    # Confirm the key helper produces the review marker when all identity fields
    # are empty (and sender is present):
    assert reply_agent._followup_task_key("j@x.in", "", "", "") == "reply_followup:<review>"
    # And that the nosender marker is unchanged:
    assert reply_agent._followup_task_key("", "", "", "") == "reply_followup:<nosender>"


def test_imap_uid_parser(tmp_path, monkeypatch):
    """_imap_uid extracts the numeric UID from the fetch envelope string."""
    # Standard IMAP envelope with UID:
    assert (
        reply_agent._imap_uid(b'1 (UID 1001 INTERNALDATE "23-Sep-2026 10:00:00 +0000" BODY[] {1})')
        == "1001"
    )
    # No UID in envelope:
    assert reply_agent._imap_uid(b'1 (INTERNALDATE "23-Sep-2026 10:00:00 +0000" BODY[] {1})') == ""
    # None input:
    assert reply_agent._imap_uid(None) == ""


# --------------------------------------------------------------------------- #
# _typesafe_content_gate
# --------------------------------------------------------------------------- #
def test_content_gate_noop_when_flag_off(monkeypatch):
    monkeypatch.setattr(typesafe_services, "get_typesafe_content_qa", lambda: _content_svc())
    out = reply_agent._typesafe_content_gate("s", "b")
    assert out == {"enabled": False}


def test_content_gate_inert_fails_open(monkeypatch):
    # Flag on but the client is INERT (no key) -> advisory only: needs_review is
    # False, so the row still proceeds to the claim/send path. We never block the
    # bounded auto-send just because the paid verifier is not armed.
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE_CONTENT", "1")
    monkeypatch.setattr(
        typesafe_services, "get_typesafe_content_qa", lambda: _content_svc(enabled=False)
    )
    out = reply_agent._typesafe_content_gate("s", "b")
    assert out["enabled"] is True
    assert out["passed"] is True
    assert out["needs_review"] is False
    assert out.get("state") == "inert"
    assert out.get("reason") == "inert"


def test_content_gate_records_clean_verdict(monkeypatch):
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE_CONTENT", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_content_qa",
        lambda: _content_svc(approved=True, tone="professional", success=True, has_answer=True),
    )
    out = reply_agent._typesafe_content_gate(
        "Re: demo", "Thanks, we can do a demo.", {"business_name": "Jiya"}
    )
    assert out["enabled"] is True
    assert out["passed"] is True
    assert out["needs_review"] is False
    assert out["compliance_violation"] is False
    assert out.get("state") == "ok"
    assert out.get("model") == "jev-1.13.0"


def test_content_gate_flags_scam_draft(monkeypatch):
    # A clean API call that REJECTS the draft -> needs_review, state "rejected".
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE_CONTENT", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_content_qa",
        lambda: _content_svc(
            approved=False,
            tone="aggressive",
            reasons=["High spam score", "Aggressive tone", "Compliance risk"],
        ),
    )
    out = reply_agent._typesafe_content_gate(
        "GUARANTEED 10x in 7 days!!", "Pay bank transfer now, no questions.", None
    )
    assert out["enabled"] is True
    assert out["passed"] is False
    assert out["compliance_violation"] is True
    assert out["needs_review"] is True
    assert out.get("state") == "rejected"


def test_content_gate_empty_answer_holds(monkeypatch):
    # API "succeeded" but returned no usable answer -> untrustworthy, must hold.
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE_CONTENT", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_content_qa",
        lambda: _content_svc(approved=True, success=True, has_answer=False),
    )
    out = reply_agent._typesafe_content_gate("Re: demo", "draft", None)
    assert out["needs_review"] is True
    assert out.get("state") == "empty_answer"


def test_content_gate_api_error_holds(monkeypatch):
    # A verifier API error / timeout == unverifiable -> hold, do NOT fail open.
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE_CONTENT", "1")

    class _ErrSvc:
        enabled = True
        client = _StubClient(True)

        def audit_outbound_message(self, *a, **k):
            raise RuntimeError("TypeSafe 503 upstream")

    # `reply_agent` calls `from app.platform.typesafe_services import
    # get_typesafe_content_qa` inside the gate, so patch the source module.
    import app.platform.typesafe_services as tsv

    monkeypatch.setattr(tsv, "get_typesafe_content_qa", lambda: _ErrSvc())
    out = reply_agent._typesafe_content_gate("Re: demo", "draft", None)
    assert out["needs_review"] is True
    assert out.get("state") == "error"
    assert out.get("passed") is False


# --------------------------------------------------------------------------- #
# End-to-end: run_reply_triage persists TypeSafe evidence on the draft row
# --------------------------------------------------------------------------- #
def _seed_imap(monkeypatch, tmp_path, body, subject="Re: Free audit"):
    import email
    import email.utils
    from datetime import datetime, timezone

    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text("", encoding="utf-8")
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {
            "owner@biz.in": {
                "business_name": "Jiya Makeover",
                "niche": "salon",
                "emailed_at": "2026-09-01T00:00:00+00:00",
            }
        },
    )
    monkeypatch.setattr(
        ra, "_prospect_map", lambda: {"owner@biz.in": {"business_name": "Jiya Makeover"}}
    )

    async def _disabled():
        return False

    monkeypatch.setattr(ra, "_reply_auto_send_enabled", _disabled)

    async def _classify(_s, _b, _h=""):
        return "interested"

    monkeypatch.setattr(ra, "_classify", _classify)

    async def _draft(*_a, **_k):
        return "Drafted reply text"

    monkeypatch.setattr(ra, "_draft", _draft)
    monkeypatch.setattr(ra, "_notify", lambda *_a, **_k: None)
    monkeypatch.setattr("app.platform.interaction_log.record", lambda **_k: None)
    monkeypatch.setattr("app.platform.objection_extractor.extract_from_reply", lambda **_k: None)
    monkeypatch.setattr("app.platform.llm_guard.scan", lambda *_a, **_k: {"suspicious": False})

    # Hermetic: neutralise the external side-effect integrations the interested
    # branch touches so no real network/DB calls leak into the test.
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr("app.platform.revenue_attribution.record_touch", lambda **_k: {"ok": True})
    monkeypatch.setattr("app.marketing.sales_pipeline.upsert_deal", lambda *_a, **_k: {})
    monkeypatch.setattr("app.marketing.cadence.enroll", lambda *_a, **_k: {})
    monkeypatch.setattr("app.marketing.journeys.emit_event", _noop)
    monkeypatch.setattr("app.integrations.ntfy.push", _noop)
    monkeypatch.setattr("app.platform.email_unsub.is_suppressed", lambda *_a, **_k: False)
    monkeypatch.setattr("app.platform.email_unsub.suppress", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "app.platform.email_warmup.record_complaint", lambda *_a, **_k: {"paused": False}
    )
    monkeypatch.setattr(
        "app.platform.email_warmup.record_bounce", lambda *_a, **_k: {"paused": False}
    )
    monkeypatch.setattr("app.platform.team.log_event", lambda *_a, **_k: None)

    msg = email.message_from_string(
        f"From: owner@biz.in\r\nSubject: {subject}\r\nMessage-ID: <imap-x@biz.in>\r\n"
        f"Date: {email.utils.format_datetime(datetime.now(timezone.utc))}\r\n\r\n{body}\r\n"
    )

    class Mailbox:
        seen = False

        def login(self, *_a):
            return None

        def select(self, *_a):
            return "OK"

        def search(self, *_a):
            return "OK", [b"" if self.seen else b"1"]

        def fetch(self, _id, spec):
            return "OK", [
                (b'1 (INTERNALDATE "23-Sep-2026 10:00:00 +0000" BODY[] {1})', msg.as_bytes())
            ]

        def store(self, *_a):
            self.seen = True
            return "OK", []

        def close(self):
            return None

        def logout(self):
            return None

    monkeypatch.setattr(ra.imaplib, "IMAP4_SSL", lambda *_a, **_k: Mailbox())
    monkeypatch.setattr(ra, "_creds", lambda: ("imap.example", "u", "p"))
    monkeypatch.setenv("REPLY_AGENT", "1")
    return f


async def test_triage_persists_typesafe_evidence_on_draft(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = _seed_imap(monkeypatch, tmp_path, "can you do a demo this week? pricing?")
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_reply_triage",
        lambda: _triage_svc("demo_request", is_hot=True, latency=1.0, model="jev-1.13.0"),
    )
    res = await ra.run_reply_triage(limit=5)
    rows = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["intent"] == "interested"  # no conflict (LLM+TypeSafe agree)
    ts = row.get("typesafe")
    assert ts is not None and ts.get("active") is True
    assert ts.get("intent") == "demo_request"
    assert ts.get("model") == "jev-1.13.0"
    # triage still drained + auto-send attempted (disabled -> 0 sent).
    assert res["processed"] >= 1


async def test_triage_conflict_demotes_to_other_and_holds(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = _seed_imap(
        monkeypatch,
        tmp_path,
        "no thanks, we are not interested please stop emailing",
        subject="Re: Free audit",
    )
    # LLM (faked above) still says 'interested'; TypeSafe is a confident unsubscribe
    # -> the caller must demote to 'other' and hold for review, not invent intent.
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_reply_triage",
        lambda: _triage_svc("unsubscribe", is_hot=False),
    )
    await ra.run_reply_triage(limit=5)
    rows = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["intent"] == "other"  # demoted, not 'interested'
    assert row["typesafe"].get("conflict") is True
    assert row["typesafe"].get("held_for_review") is True


def test_auto_send_typesafe_content_gate_blocks(tmp_path, monkeypatch):
    """Armed content gate: a rejecting verdict (approved=False) HOLDS the row for
    review — no send, no claim burned, nothing actually goes out."""
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text(
        json.dumps(
            {
                "from": "owner@biz.in",
                "subject": "Re: demo",
                "intent": "interested",
                "draft": "Great draft",
                "draft_source": "llm",
                "channel": "email",
                "message_id": "<m@x>",
                "delivery_key": "owner@biz.in::<m@x>",
                "source_at": "2026-09-20T00:00:00+00:00",
                "scan_status": "clean",
                "at": "2026-09-23T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {"owner@biz.in": {"emailed_at": "2026-09-20T00:00:00+00:00"}},
    )

    async def _enabled():
        return True

    monkeypatch.setattr(ra, "_reply_auto_send_enabled", _enabled)

    claims = []

    async def _claim(_k, _c):
        claims.append(_k)
        return 1

    async def _release(_k):
        return None

    sent = []

    async def _sender(frm, subject, body, headers):
        sent.append(frm)
        return True

    monkeypatch.setattr(ra, "_send_reply_email", _sender)
    # Let the deterministic pre-gates pass so the row reaches the content gate.
    monkeypatch.setattr("app.platform.email_unsub.is_suppressed", lambda *_a, **_k: False)
    monkeypatch.setattr("app.platform.team.log_event", lambda *_a, **_k: None)

    # Armed content gate + a rejecting verdict (approved=False) -> HOLD, do not send.
    monkeypatch.setenv("REPLY_AGENT_TYPESAFE_CONTENT", "1")
    monkeypatch.setattr(
        typesafe_services,
        "get_typesafe_content_qa",
        lambda: _content_svc(approved=False, tone="aggressive", reasons=["compliance risk"]),
    )

    async def _run():
        return await ra.run_auto_reply_backlog(
            limit=3, send_fn=_sender, claim_fn=_claim, release_unattempted_fn=_release
        )

    out = _run_and_return(_run)
    assert out["sent"] == 0
    assert out.get("held_for_review") == 1
    assert sent == []  # nothing actually sent
    # The row was held BEFORE the idempotency claim was consumed.
    assert claims == []


def _run_and_return(coro_factory):
    """Run an async factory hermetically without leaking the event loop."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()
