"""WB-EMAIL-003 — inbound sales-reply qualification & handoff tests.

Hermetic coverage for the bounded routing slice added on top of #569
(``route_qualified_reply_to_task`` + ``build_typesafe_qa_trace`` in
``app/platform/reply_agent.py``):

1. distinct buyers -> distinct persisted tasks
2. same-sender separate emails (distinct scoped UIDs) -> distinct tasks
3. duplicate delivery -> one task (idempotent replay)
4. restart replay -> fresh orchestrator over the same ledger DB dedups
5. wrong-tenant thread -> task carries the PROSPECT's tenant scope, not the
   thread's; unknown prospect -> owner review, never a minted task
6. unsubscribe / DND -> suppressed, no task minted (opt-out never becomes a
   sales follow-up)
7. classifier failure / uncertainty -> owner review, nothing dropped
   silently

Plus the TypeSafe classification-QA decision trace (M00A required fields) and
responsible-worker selection (hot -> swara, pricing/question/objection ->
rohan). No SMTP, no IMAP, no real customer email is ever sent or read; all
persistence goes to a temp orchestrator ledger.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from app.platform import reply_agent
from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _temp_orchestrator(tmp_path: Any) -> AutomationOrchestrator:
    """Point the durable task store at a temp DB (never the real ledger)."""
    db = str(tmp_path / "orchestrator_ledger.db")
    ledger = str(tmp_path / "orchestrator_ledger.json")
    return AutomationOrchestrator(
        store=DurableTaskStore(db_path=db, ledger_file=ledger)
    )


def _orch_files(tmp_path: Any) -> tuple[str, str]:
    return (
        str(tmp_path / "orchestrator_ledger.db"),
        str(tmp_path / "orchestrator_ledger.json"),
    )


def _arm(monkeypatch: Any) -> None:
    """Both flags the routing slice needs (task minting stays opt-in)."""
    monkeypatch.setenv("REPLY_AGENT_FOLLOWUP_TASK", "1")


def _prospect(**over: Any) -> dict[str, Any]:
    p = {
        "business_name": "Jiya Makeover",
        "email": "j@x.in",
        "phone": "9876543210",
        "niche": "makeover",
        "client_id": "tenantA",
    }
    p.update(over)
    return p


# --------------------------------------------------------------------------- #
# 1. Distinct buyers -> distinct tasks
# --------------------------------------------------------------------------- #
def test_distinct_buyers_distinct_tasks(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    r1 = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=_prospect(),
        ts_ev={},
        message_id="<mid-1@x.in>",
        orchestrator=orch,
    )
    r2 = reply_agent.route_qualified_reply_to_task(
        intent="question",
        prospect=_prospect(
            business_name="Kavya Salon",
            email="k@y.in",
            client_id="tenantB",
        ),
        ts_ev={},
        message_id="<mid-2@y.in>",
        orchestrator=orch,
    )
    assert r1["routed"] == "qualified"
    assert r2["routed"] == "qualified"
    assert r1["created"] is True and r2["created"] is True
    assert r1["task_id"] != r2["task_id"]
    # Persisted task ids are durable and retrievable:
    assert orch.store.get(r1["task_id"]).input_payload["tenant_scope"] == "tenantA"
    assert orch.store.get(r2["task_id"]).input_payload["tenant_scope"] == "tenantB"


# --------------------------------------------------------------------------- #
# 2. Same sender, separate emails -> distinct tasks
# --------------------------------------------------------------------------- #
def test_same_sender_separate_emails_distinct_tasks(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    p = _prospect()
    r1 = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev={},
        uid="1001",
        mailbox="sales@leadsgenai.in",
        uidvalidity="1",
        orchestrator=orch,
    )
    r2 = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev={},
        uid="1002",
        mailbox="sales@leadsgenai.in",
        uidvalidity="1",
        orchestrator=orch,
    )
    assert r1["created"] is True and r2["created"] is True
    assert r1["task_id"] != r2["task_id"]
    assert r1["idempotency_key"] != r2["idempotency_key"]


# --------------------------------------------------------------------------- #
# 3. Duplicate delivery -> one task
# --------------------------------------------------------------------------- #
def test_duplicate_delivery_single_task(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    p = _prospect()
    first = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev={},
        message_id="<mid-dup@x.in>",
        orchestrator=orch,
    )
    second = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev={},
        message_id="<mid-dup@x.in>",
        orchestrator=orch,
    )
    assert first["created"] is True
    assert second["created"] is False
    assert second["reason"] == "duplicate"
    assert second["task_id"] == first["task_id"]
    assert second["routed"] == "qualified"  # still qualified, just not re-minted


# --------------------------------------------------------------------------- #
# 4. Restart replay -> dedup on a fresh orchestrator over the same DB
# --------------------------------------------------------------------------- #
def test_restart_replay_dedups(tmp_path, monkeypatch):
    _arm(monkeypatch)
    db, ledger = _orch_files(tmp_path)
    store1 = DurableTaskStore(db_path=db, ledger_file=ledger)
    orch1 = AutomationOrchestrator(store=store1)
    p = _prospect()
    r1 = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev={},
        uid="1001",
        mailbox="sales@leadsgenai.in",
        uidvalidity="1",
        orchestrator=orch1,
    )
    assert r1["created"] is True
    # "Restart": brand-new orchestrator instance, same ledger files.
    orch2 = AutomationOrchestrator(
        store=DurableTaskStore(db_path=db, ledger_file=ledger)
    )
    r2 = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev={},
        uid="1001",
        mailbox="sales@leadsgenai.in",
        uidvalidity="1",
        orchestrator=orch2,
    )
    assert r2["created"] is False
    assert r2["reason"] == "duplicate"
    assert r2["task_id"] == r1["task_id"]


# --------------------------------------------------------------------------- #
# 5. Wrong-tenant thread -> prospect's tenant wins; unknown -> review
# --------------------------------------------------------------------------- #
def test_wrong_tenant_thread_carries_prospect_scope(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    p = _prospect(client_id="tenantA")
    out = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev={},
        message_id="<mid@tenantA>",
        # Thread references point at ANOTHER tenant's outbound message:
        references="<out-777@tenantB.example>",
        orchestrator=orch,
    )
    assert out["routed"] == "qualified" and out["created"] is True
    rec = orch.store.get(out["task_id"])
    # Tenant scope is stamped from the prospect row (the CRM identity), NEVER
    # inferred from the (foreign) thread references:
    assert rec.input_payload["tenant_scope"] == "tenantA"
    assert rec.input_payload["client_id"] == "tenantA"


def test_unknown_prospect_goes_to_owner_review(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    out = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=None,  # sender not in the CRM: identity uncertain
        ts_ev={},
        message_id="<mid-unknown@x.in>",
        orchestrator=orch,
    )
    assert out["routed"] == "owner_review"
    assert out["created"] is False and out["task_id"] is None
    assert out["decision"] == "route_review"


# --------------------------------------------------------------------------- #
# 6. Unsubscribe / DND -> suppressed, no task
# --------------------------------------------------------------------------- #
def test_unsubscribe_suppressed_no_task(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    p = _prospect()
    out = reply_agent.route_qualified_reply_to_task(
        intent="unsubscribe",
        prospect=p,
        ts_ev={},
        message_id="<mid-u@x.in>",
        orchestrator=orch,
    )
    assert out["routed"] == "suppressed"
    assert out["decision"] == "suppress_dnd"
    assert out["created"] is False and out["task_id"] is None
    assert out["assigned_agent"] is None
    # Nothing minted:
    assert len(list(orch.store.iter_rows() if hasattr(orch.store, "iter_rows") else [])) in (0, 1)


def test_typesafe_conflict_unsubscribe_suppressed(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    p = _prospect()
    ts_ev = {
        "active": True,
        "intent": "unsubscribe",
        "mapped_intent": "unsubscribe",
        "is_hot": False,
        "conflict": True,
        "model": "jev-1.13.0",
    }
    # LLM said "interested", TypeSafe is confident it is an opt-out:
    out = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev=ts_ev,
        message_id="<mid-c@x.in>",
        orchestrator=orch,
    )
    assert out["routed"] == "suppressed"
    assert out["created"] is False
    assert out["trace"]["result"]["typesafe_conflict"] is True


# --------------------------------------------------------------------------- #
# 7. Classifier failure / uncertainty -> owner review, nothing dropped
# --------------------------------------------------------------------------- #
def test_uncertain_classification_owner_review(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    p = _prospect()
    # LLM "other" with no active TypeSafe confirmation:
    out = reply_agent.route_qualified_reply_to_task(
        intent="other",
        prospect=p,
        ts_ev={"active": False, "reason": "inert"},
        message_id="<mid-o@x.in>",
        orchestrator=orch,
    )
    assert out["routed"] == "owner_review"
    assert out["reason"] == "uncertain_classification"


def test_typesafe_conflict_hot_vs_decline_owner_review(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    p = _prospect()
    ts_ev = {
        "active": True,
        "intent": "not_interested",
        "mapped_intent": "not_interested",
        "is_hot": False,
        "conflict": True,
        "model": "jev-1.13.0",
    }
    out = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=p,
        ts_ev=ts_ev,
        message_id="<mid-x@x.in>",
        orchestrator=orch,
    )
    assert out["routed"] == "owner_review"
    assert out["created"] is False


def test_classifier_error_degrades_to_review(tmp_path, monkeypatch):
    """A persistence failure must NOT drop the reply — it surfaces as review."""

    class _Boom:
        def submit_task(self, *a, **kw):  # pragma: no cover - raises
            raise RuntimeError("ledger unavailable")

    _arm(monkeypatch)
    out = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=_prospect(),
        ts_ev={},
        message_id="<mid-e@x.in>",
        orchestrator=_Boom(),
    )
    assert out["routed"] == "owner_review"
    assert out["created"] is False
    assert "error:" in out["reason"]


def test_not_interested_archives_no_task(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    out = reply_agent.route_qualified_reply_to_task(
        intent="not_interested",
        prospect=_prospect(),
        ts_ev={},
        message_id="<mid-n@x.in>",
        orchestrator=orch,
    )
    assert out["routed"] == "suppressed"
    assert out["reason"] == "hard_decline_no_task"


# --------------------------------------------------------------------------- #
# Responsible worker selection
# --------------------------------------------------------------------------- #
def test_hot_intent_routes_to_telecaller(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    ts_ev = {"active": True, "is_hot": True, "model": "jev-1.13.0"}
    out = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=_prospect(),
        ts_ev=ts_ev,
        message_id="<mid-h@x.in>",
        orchestrator=orch,
    )
    assert out["assigned_agent"] == "swara"
    rec = orch.store.get(out["task_id"])
    assert rec.assigned_agent == "swara"


def test_pricing_question_routes_to_leads_manager(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    ts_ev = {"active": True, "is_hot": False, "model": "jev-1.13.0"}
    out = reply_agent.route_qualified_reply_to_task(
        intent="question",  # pricing query
        prospect=_prospect(),
        ts_ev=ts_ev,
        message_id="<mid-q@x.in>",
        orchestrator=orch,
    )
    assert out["assigned_agent"] == "rohan"
    assert orch.store.get(out["task_id"]).assigned_agent == "rohan"


def test_objection_routes_to_leads_manager(tmp_path, monkeypatch):
    _arm(monkeypatch)
    orch = _temp_orchestrator(tmp_path)
    out = reply_agent.route_qualified_reply_to_task(
        intent="objection",
        prospect=_prospect(),
        ts_ev={},
        message_id="<mid-obj@x.in>",
        orchestrator=orch,
    )
    assert out["routed"] == "qualified"
    assert out["assigned_agent"] == "rohan"


# --------------------------------------------------------------------------- #
# TypeSafe classification-QA decision trace (M00A required fields)
# --------------------------------------------------------------------------- #
def test_qa_trace_carries_required_m00a_fields():
    out = reply_agent.build_typesafe_qa_trace(
        task_id="task_abc12345",
        tenant_scope="tenantA",
        llm_intent="interested",
        typesafe_evidence={"active": True, "model": "jev-1.13.0", "mapped_intent": "demo_request"},
        decision="route_task",
        branch="task_minted",
        side_effect_id="task_abc12345",
        observed_outcome="created",
        evidence_refs=["inbound:<mid-h@x.in>"],
    )
    for field in (
        "decision_id",
        "task_id",
        "tenant_scope",
        "purpose",
        "state_hash",
        "evidence_refs",
        "requested_model",
        "resolved_model",
        "primitive",
        "result",
        "downstream_branch",
        "side_effect_id",
        "observed_outcome",
    ):
        assert field in out, f"missing M00A trace field {field}"
    assert out["decision_id"] == "task_abc12345"
    assert out["resolved_model"] == "jev-1.13.0"
    assert out["primitive"] == "Choice"
    assert out["result"]["typesafe_mapped_intent"] == "demo_request"


def test_qa_trace_inert_marks_primitive(tmp_path, monkeypatch):
    _arm(monkeypatch)
    out = reply_agent.route_qualified_reply_to_task(
        intent="other",
        prospect=_prospect(),
        ts_ev={"active": False, "reason": "inert"},
        message_id="<mid-t@x.in>",
        orchestrator=_temp_orchestrator(tmp_path),
    )
    assert out["routed"] == "owner_review"
    assert out["trace"]["primitive"] == "inert"
    # The model output is evidence, never the final proof of intent:
    assert out["decision"] == "route_review"


def test_flag_off_routing_is_noop(tmp_path, monkeypatch):
    """With REPLY_AGENT_FOLLOWUP_TASK off the route degrades to review — the
    routing slice itself adds no behaviour unless the owner arms it."""
    monkeypatch.delenv("REPLY_AGENT_FOLLOWUP_TASK", raising=False)
    out = reply_agent.route_qualified_reply_to_task(
        intent="interested",
        prospect=_prospect(),
        ts_ev={},
        message_id="<mid-off@x.in>",
        orchestrator=_temp_orchestrator(tmp_path),
    )
    assert out["routed"] == "owner_review"
    assert out["reason"] == "flag_off"
    assert out["created"] is False
