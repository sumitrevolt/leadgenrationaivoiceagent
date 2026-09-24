"""P0-76 owner-ACK handler — T1-T4 targeted tests.

Conventions: follow tests/test_telegram_integration_2026.py (mocked updates,
send_reply=False, orchestrator + dev_workers monkeypatched, no live network, no
VPS poller contact). All four tests assert the four evidence fields the DONE
gate needs: inbound update_id, task transition, worker result, outgoing message_id.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.integrations.telegram_bot import TelegramBot
from app.integrations.telegram_p0_76_ack import (
    P0_76_APPROVAL_TEXT,
    P0_76_EXPECTED_OWNER_BOT,
    P0_76_IDEMPOTENCY_KEY,
    P0_76_OWNER_CHAT_ID,
    P076Result,
    _compute_p0_76_execution,
    handle_p0_76_ack,
    handle_p0_76_review_approval,
    is_p0_76_ack,
    is_p0_76_approval,
)
from app.platform.automation_orchestrator import TaskPriority, TaskStatus

ACK_TEXT = "P0-76 ACK"


def _owner_update(
    update_id: int,
    text: str,
    chat_id: int = P0_76_OWNER_CHAT_ID,
    user_id: int = 1,
    username: str = "sumitdaryanani",
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 100 + (update_id % 10),
            "chat": {"id": chat_id, "type": "private", "first_name": "sumit"},
            "from": {"id": user_id, "username": username},
            "text": text,
        },
    }


def _foreign_update(
    update_id: int, text: str, chat_id: int = 999, user_id: int = 4242, username: str = "outsider"
) -> dict:
    return _owner_update(update_id, text, chat_id=chat_id, user_id=user_id, username=username)


@pytest.fixture()
def p076_env(tmp_path, monkeypatch):
    """Isolated orchestrator + bot + coordinator globals for P0-76 tests."""
    from app.platform import automation_orchestrator as ao
    from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore

    store = DurableTaskStore(
        db_path=str(tmp_path / "p076_ledger.db"), ledger_file=str(tmp_path / "p076_ledger.json")
    )
    orch = AutomationOrchestrator(
        store=store, lease_file=str(tmp_path / "p076_leases.json"), dev_worker_store=None
    )
    orch._dev_worker_store = MagicMock(name="dev_workers")
    orch.dev_workers = orch._dev_worker_store

    # Seed the EXISTING bound task (task_79406871) in READY state.
    from app.platform.automation_orchestrator import TaskRecord

    seed = TaskRecord(
        task_id="task_79406871",
        owner_bot="guardian",
        assigned_agent="hermes",
        priority=TaskPriority.LOW,
        status=TaskStatus.READY,
        version=1,
        idempotency_key=P0_76_IDEMPOTENCY_KEY,
        input_payload={"admin_task_ref": 76},
        fencing_token=None,
    )
    store.save(seed)
    # Seed task's priority enum must be valid: TaskRecord init uses TaskPriority (mocked above).

    # Bot with owner chat pinned to the P0-76 owner chat only (no live network).
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_IDS", str(P0_76_OWNER_CHAT_ID))
    monkeypatch.setenv("TELEGRAM_OWNER_USERNAMES", "sumitdaryanani")
    bot = TelegramBot.__new__(TelegramBot)
    bot.token = "test-token"
    bot._processed_updates = {}
    bot._bot_info = {"first_name": "Jarvis"}
    bot.orchestrator = orch

    # Coordinator dedupe: a fresh in-memory set so each test is independent.
    import app.platform.telegram_coordinator as tc

    _dedupe = set()

    def _fake_dup(update_id):
        if update_id in _dedupe:
            return True
        _dedupe.add(update_id)
        return False

    monkeypatch.setattr(tc, "is_duplicate_update", lambda uid: _fake_dup(uid))

    # Evidence artifacts for the worker-execution step.
    ev_root = tmp_path / "evidence"
    ev_root.mkdir()
    (ev_root / "verifier_json_20260923.json").write_text(
        json.dumps({"credentials": {"jarvis": {"valid": True}}}), encoding="utf-8"
    )
    (ev_root / "typesafe_call_trace_20260923.json").write_text(
        json.dumps(
            {
                "api_call_success": True,
                "resolved_model": "jev-1.13.0",
                "primary_value": "fix_group_wiring",
            }
        ),
        encoding="utf-8",
    )
    (ev_root / "P0_76_CODE_HANDOFF.md").write_text(
        "# P0-76 code handoff (test artifact)", encoding="utf-8"
    )
    monkeypatch.setenv("P0_76_EVIDENCE_DIR", str(ev_root))

    # Egress: capture ACK sends without network.
    sent: list[dict] = []
    orch_call_count = {"dispatch": 0, "verify": 0}

    def _fake_dispatch(task_id):
        orch_call_count["dispatch"] += 1
        rec = store.get(task_id)
        rec.status = TaskStatus.RUNNING
        store.save(rec)
        orch.dev_workers.claim(task_id, lease_token=rec.fencing_token or "")
        return True

    def _fake_verify(
        task_id, execution_evidence=None, is_success=True, error_msg=None, fencing_token=None
    ):
        orch_call_count["verify"] += 1
        rec = store.get(task_id)
        rec.evidence = (
            execution_evidence.to_dict()
            if hasattr(execution_evidence, "to_dict")
            else execution_evidence
        )
        rec.status = TaskStatus.DONE if is_success else TaskStatus.FAILED
        store.save(rec)
        orch.dev_workers.finish(task_id, success=is_success, evidence=str(execution_evidence))
        return rec

    monkeypatch.setattr(orch, "dispatch_task", _fake_dispatch)
    monkeypatch.setattr(orch, "verify_and_complete", _fake_verify)

    def _fake_jarvis_response(chat_id, text, parse_mode="HTML"):
        sent.append({"chat_id": chat_id, "text": text, "message_id": 90000 + len(sent)})
        return {"ok": True, "result": {"message_id": 90000 + len(sent) - 1}}

    monkeypatch.setattr(tc, "dispatch_jarvis_response", _fake_jarvis_response)
    return {
        "orch": orch,
        "bot": bot,
        "store": store,
        "dev_workers": orch.dev_workers,
        "sent": sent,
        "counts": orch_call_count,
        "tc": tc,
    }


def test_is_p0_76_ack_normalization():
    assert is_p0_76_ack("P0-76 ACK")
    assert is_p0_76_ack("p0-76 ack")
    assert is_p0_76_ack("  P0-76 ACK  ")
    assert not is_p0_76_ack("P0-76")
    assert not is_p0_76_ack("P0-76 ACKS")
    assert not is_p0_76_ack("")
    assert not is_p0_76_ack(None)


def test_t1_idempotent_ack(p076_env):
    """First ACK claims the task, completes it, and sends exactly one ACK.
    A second ACK (new update_id) is a NO-OP returning the cached state —
    no second dispatch, no second verify, no second egress message."""
    env = p076_env
    r1 = handle_p0_76_ack(
        bot=env["bot"],
        orchestrator=env["orch"],
        update=_owner_update(1, ACK_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_ack=True,
    )
    assert r1.task_found and r1.task_id == "task_79406871"
    assert r1.worker_claimed
    assert r1.task_final_status == str(TaskStatus.DONE)
    assert r1.ack_sent and r1.ack_message_id is not None
    assert env["counts"]["dispatch"] == 1 and env["counts"]["verify"] == 1
    assert len(env["sent"]) == 1

    # second ACK (fresh update_id) must NOT re-execute or re-send
    r2 = handle_p0_76_ack(
        bot=env["bot"],
        orchestrator=env["orch"],
        update=_owner_update(2, ACK_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_ack=True,
    )
    assert r2.completed_by_state
    assert r2.cached_ack_message_id == r1.ack_message_id
    assert r2.ack_sent is False
    assert env["counts"]["dispatch"] == 1 and env["counts"]["verify"] == 1
    assert len(env["sent"]) == 1, "no duplicate ACK"


def test_t2_unauthorized_sender(p076_env):
    """A non-owner sender is denied: no task claim, no worker, no egress, no audit-suppressed result."""
    env = p076_env
    r = handle_p0_76_ack(
        bot=env["bot"],
        orchestrator=env["orch"],
        update=_foreign_update(1, ACK_TEXT),
        chat_id=999,
        send_ack=True,
    )
    assert r.authorized is False
    assert r.task_found is False
    assert r.worker_claimed is False
    assert r.ack_sent is False and r.ack_message_id is None
    assert env["counts"]["dispatch"] == 0 and env["counts"]["verify"] == 0
    assert len(env["sent"]) == 0
    # The bound task is untouched
    rec = env["orch"].store.get_by_idempotency_key(P0_76_IDEMPOTENCY_KEY)
    assert rec.status == TaskStatus.READY


def test_t3_replay_same_update_id(p076_env):
    """Same update_id delivered twice: the second is a dedupe no-op returning cached state."""
    env = p076_env
    r1 = handle_p0_76_ack(
        bot=env["bot"],
        orchestrator=env["orch"],
        update=_owner_update(7, ACK_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_ack=True,
    )
    assert r1.ack_sent
    r2 = handle_p0_76_ack(
        bot=env["bot"],
        orchestrator=env["orch"],
        update=_owner_update(7, ACK_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_ack=True,
    )
    assert r2.deduplicated
    assert r2.task_found and r2.task_id == "task_79406871"
    assert r2.cached_ack_message_id == r1.ack_message_id
    # Exactly one execution + one ACK
    assert env["counts"]["dispatch"] == 1 and env["counts"]["verify"] == 1
    assert len(env["sent"]) == 1


def test_t4_scope_mismatch_fail_closed(p076_env, monkeypatch):
    """A bound task under the WRONG owner_bot scope (cross-tenant) is a
    fail-closed worker failure: no fake success, no ACK, task not DONE.

    The store treats owner_bot as IMMUTABLE after creation (upsert does not
    update it), so to exercise the guard we DELETE + re-insert the task with
    a mismatched owner_bot directly via the underlying SQLite connection.
    """
    import sqlite3

    env = p076_env
    store = env["orch"].store
    db_path = store.db_path

    # Replace the seeded task with one under the WRONG owner_bot.
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM task_records WHERE task_id = ?", ("task_79406871",))
    conn.execute(
        """INSERT INTO task_records (
            task_id, owner_bot, assigned_agent, priority, status, version,
            fencing_token, retry_count, max_retries, deadline_s, provider,
            model, idempotency_key, input_payload, evidence, error_message,
            last_heartbeat, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 3, 300, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "task_79406871",
            "cross_tenant_bot",  # WRONG owner_bot (not P0_76_EXPECTED_OWNER_BOT)
            "hermes",
            "LOW",
            "READY",
            1,
            None,
            "leadgen",
            "m1",
            P0_76_IDEMPOTENCY_KEY,
            '{"admin_task_ref": 76}',
            None,
            None,
            0.0,
            0.0,
            0.0,
        ),
    )
    conn.commit()
    conn.close()

    r = handle_p0_76_ack(
        bot=env["bot"],
        orchestrator=env["orch"],
        update=_owner_update(1, ACK_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_ack=True,
    )
    assert r.error == "scope_mismatch"
    assert r.ack_sent is False and r.ack_message_id is None
    assert "scope" in r.response_text.lower()
    assert len(env["sent"]) == 0, "no ACK on scope-mismatch failure"
    # The bound task must NOT be DONE.
    final = store.get_by_idempotency_key(P0_76_IDEMPOTENCY_KEY)
    assert final is not None
    assert final.status != TaskStatus.DONE, "cross-tenant task must not be DONE"


def test_command_linked_fingerprint_distinct(p076_env):
    """Two different inbound update_ids on the same task produce DIFFERENT
    execution fingerprints (command-linked proof, not a static file read)."""
    a = _compute_p0_76_execution(
        task_id="task_79406871",
        update_id=11,
        fencing_token="fence_task_79406871_1_0",  # nosecret: deterministic test-fixture fencing token (not a real secret)
        owner_bot=P0_76_EXPECTED_OWNER_BOT,
    )
    bfp = _compute_p0_76_execution(
        task_id="task_79406871",
        update_id=22,
        fencing_token="fence_task_79406871_1_0",  # nosecret: deterministic test-fixture fencing token (not a real secret)
        owner_bot=P0_76_EXPECTED_OWNER_BOT,
    )
    cfp = _compute_p0_76_execution(
        task_id="task_79406871",
        update_id=11,
        fencing_token="fence_task_79406871_2_0",  # fresh claim token  # nosecret: deterministic test-fixture fencing token (not a real secret)
        owner_bot=P0_76_EXPECTED_OWNER_BOT,
    )
    assert a["execution_fingerprint"] != bfp["execution_fingerprint"]
    assert a["execution_fingerprint"] != cfp["execution_fingerprint"]
    assert a["inbound_update_id"] == 11 and bfp["inbound_update_id"] == 22


def test_typesafe_enabled_review_verdict_on_task_79406871(tmp_path, monkeypatch):
    """With TypeSafe ENABLED and a controlled policy client returning
    route=review, dispatch of the LIVE target task_79406871 must land in
    REVIEW EXACTLY (honest gate outcome) - not faked into RUNNING.

    Exercises the REAL judge_task() policy path with a controlled client, so
    the REVIEW verdict is PROVEN for task_79406871 (not the historical
    task_ffbbe8bc trace)."""
    from types import SimpleNamespace

    from app.platform.automation_orchestrator import (
        AutomationOrchestrator,
        DurableTaskStore,
        TaskPriority,
        TaskRecord,
    )
    from app.platform.dev_workers import DevWorkerStore

    db = str(tmp_path / "policy_ledger.db")
    store = DurableTaskStore(db_path=db, ledger_file=str(tmp_path / "policy_ledger.json"))
    orch = AutomationOrchestrator(
        store=store,
        lease_file=str(tmp_path / "policy_lease.json"),
        dev_worker_store=DevWorkerStore(db_path=db),
    )
    seed = TaskRecord(
        task_id="task_79406871",
        owner_bot=P0_76_EXPECTED_OWNER_BOT,
        assigned_agent="hermes",
        priority=TaskPriority.LOW,
        status=TaskStatus.READY,
        version=1,
        idempotency_key=P0_76_IDEMPOTENCY_KEY,
        input_payload={"admin_task_ref": 76},
        fencing_token=None,
    )
    store.save(seed)

    monkeypatch.setenv("TYPESAFE_ENABLED", "1")

    fake_response = SimpleNamespace(
        success=True,
        model="jev-latest",
        answers={"route": {"choice": "review"}},
    )
    fake_client = SimpleNamespace(
        enabled=True,
        model="jev-latest",
        system_one=lambda *a, **k: fake_response,
    )
    import app.platform.typesafe_session_policy as tsp
    monkeypatch.setattr(tsp, "get_typesafe_client", lambda: fake_client)

    dispatched = orch.dispatch_task("task_79406871")
    rec = store.get("task_79406871")
    assert dispatched is False, "review verdict must NOT dispatch to RUNNING"
    assert rec.status == TaskStatus.REVIEW, "task must land in REVIEW exactly"
    assert "TypeSafe session policy" in (rec.error_message or "")


def test_owner_review_approval_releases_to_ready(tmp_path, monkeypatch):
    """CANONICAL task-specific approval: owner 'P0-76 APPROVE' on a REVIEW
    task -> CAS REVIEW->READY with a FRESH fencing token + durable audit in
    task evidence. Non-owner is DENIED. No blanket bypass (kill switch /
    RED lane re-checked as deterministic gates)."""
    from app.platform import telegram_coordinator as tc
    from app.platform.automation_orchestrator import (
        AutomationOrchestrator,
        DurableTaskStore,
        TaskPriority,
        TaskRecord,
    )
    from app.platform.dev_workers import DevWorkerStore

    db = str(tmp_path / "appr_ledger.db")
    store = DurableTaskStore(db_path=db, ledger_file=str(tmp_path / "appr_ledger.json"))
    orch = AutomationOrchestrator(
        store=store,
        lease_file=str(tmp_path / "appr_lease.json"),
        dev_worker_store=DevWorkerStore(db_path=db),
    )
    seed = TaskRecord(
        task_id="task_79406871",
        owner_bot=P0_76_EXPECTED_OWNER_BOT,
        assigned_agent="hermes",
        priority=TaskPriority.LOW,
        status=TaskStatus.REVIEW,
        version=1,
        idempotency_key=P0_76_IDEMPOTENCY_KEY,
        input_payload={"admin_task_ref": 76},
        fencing_token="fence_task_79406871_stale_0",  # nosecret: deterministic test-fixture fencing token (not a real secret)
        error_message="TypeSafe session policy requires owner review",
    )
    store.save(seed)
    old_token = seed.fencing_token

    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_IDS", str(P0_76_OWNER_CHAT_ID))
    monkeypatch.setenv("TELEGRAM_OWNER_USERNAMES", "sumitdaryanani")
    bot = TelegramBot.__new__(TelegramBot)
    bot.token = "test-token"
    bot._processed_updates = {}
    bot._bot_info = {"first_name": "Jarvis"}
    bot.orchestrator = orch

    _dedupe = set()

    def _fake_dup(uid):
        if uid in _dedupe:
            return True
        _dedupe.add(uid)
        return False

    monkeypatch.setattr(tc, "is_duplicate_update", lambda uid: _fake_dup(uid))
    sent = []

    def _fake_jarvis(chat_id, text, parse_mode="HTML"):
        sent.append({"message_id": 95000 + len(sent)})
        return {"ok": True, "result": {"message_id": 95000 + len(sent) - 1}}

    monkeypatch.setattr(tc, "dispatch_jarvis_response", _fake_jarvis)

    # Non-owner DENIED: no state change, no new token.
    denied = handle_p0_76_review_approval(
        bot=bot,
        orchestrator=orch,
        update=_foreign_update(1, P0_76_APPROVAL_TEXT),
        chat_id=999,
        send_reply=False,
    )
    assert denied.authorized is False
    assert denied.error == "unauthorized"
    rec_after = store.get("task_79406871")
    assert rec_after.status == TaskStatus.REVIEW
    assert rec_after.fencing_token == old_token, "non-owner must not change the token"

    # Owner APPROVE: REVIEW -> READY with a FRESH token + durable audit.
    ok = handle_p0_76_review_approval(
        bot=bot,
        orchestrator=orch,
        update=_owner_update(1, P0_76_APPROVAL_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_reply=True,
    )
    assert ok.approved and ok.released_from_review
    assert ok.new_fencing_token and ok.new_fencing_token != old_token
    final = store.get("task_79406871")
    assert final.status == TaskStatus.READY
    assert final.fencing_token == ok.new_fencing_token
    assert final.error_message is None, "stale review error cleared on approval"
    approvals = final.evidence.get("approvals") or []
    assert any(a.get("approved") and a.get("reason") == "owner_review_approval" for a in approvals)


def test_full_chain_real_store_real_worker(tmp_path, monkeypatch):
    """FULL CHAIN on the REAL DurableTaskStore + REAL DevWorkerStore + real governor.

    inbound owner update -> existing task_79406871 bound by idempotency key ->
    REAL dispatch_task (fresh fencing token + real lease + real dev_workers
    claim row) -> command-specific real evidence verification -> REAL
    verify_and_complete (StructuredEvidence -> DONE + dev_workers done row) ->
    persisted ACK message_id inside the task record.

    Nothing on the dispatch/verify/governor/claim/finish path is faked; only
    the two network edges are captured (coordinator dedupe set + jarvis egress
    message_id). Deterministic policy env: TYPESAFE_ENABLED=0 makes judge_task
    return the documented policy_disabled/proceed degradation (no live model
    call, no global bypass of the gate code itself).
    """
    import json
    import sqlite3

    from app.platform import automation_orchestrator as ao
    from app.platform import telegram_coordinator as tc
    from app.platform.automation_orchestrator import (
        AutomationOrchestrator,
        DurableTaskStore,
        TaskPriority,
        TaskRecord,
        TaskStatus,
    )
    from app.platform.dev_workers import DevWorkerStore

    db_path = str(tmp_path / "fullchain_ledger.db")
    store = DurableTaskStore(db_path=db_path, ledger_file=str(tmp_path / "fullchain_ledger.json"))
    orch = AutomationOrchestrator(
        store=store,
        lease_file=str(tmp_path / "fullchain_lease.json"),
        dev_worker_store=DevWorkerStore(db_path=db_path),
    )

    # Seed the EXISTING bound task (task_79406871) in READY — the same
    # canonical task the live owner-ACK protocol targets. No new task is
    # created anywhere in this chain.
    seed = TaskRecord(
        task_id="task_79406871",
        owner_bot="guardian",
        assigned_agent="hermes",
        priority=TaskPriority.LOW,
        status=TaskStatus.READY,
        version=1,
        idempotency_key=P0_76_IDEMPOTENCY_KEY,
        input_payload={"admin_task_ref": 76},
        fencing_token=None,
    )
    store.save(seed)

    monkeypatch.setenv("TYPESAFE_ENABLED", "0")
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_IDS", str(P0_76_OWNER_CHAT_ID))
    monkeypatch.setenv("TELEGRAM_OWNER_USERNAMES", "sumitdaryanani")

    bot = TelegramBot.__new__(TelegramBot)
    bot.token = "test-token"
    bot._processed_updates = {}
    bot._bot_info = {"first_name": "Jarvis"}
    bot.orchestrator = orch

    _dedupe: set = set()

    def _fake_dup(update_id):
        if update_id in _dedupe:
            return True
        _dedupe.add(update_id)
        return False

    monkeypatch.setattr(tc, "is_duplicate_update", lambda uid: _fake_dup(uid))

    # Real on-disk evidence artifacts for the command-specific worker step.
    ev_root = tmp_path / "evidence_fullchain"
    ev_root.mkdir()
    (ev_root / "verifier_json_20260923.json").write_text(
        json.dumps({"credentials": {"jarvis": {"valid": True}}}), encoding="utf-8"
    )
    (ev_root / "typesafe_call_trace_20260923.json").write_text(
        json.dumps({"api_call_success": True, "resolved_model": "jev-latest"}), encoding="utf-8"
    )
    (ev_root / "P0_76_CODE_HANDOFF.md").write_text("# handoff", encoding="utf-8")
    monkeypatch.setenv("P0_76_EVIDENCE_DIR", str(ev_root))

    # Egress edge only: capture the single ACK send and its Telegram message_id.
    sent: list[dict] = []

    def _fake_jarvis_response(chat_id, text, parse_mode="HTML"):
        sent.append({"chat_id": chat_id, "text": text, "message_id": 91000 + len(sent)})
        return {"ok": True, "result": {"message_id": 91000 + len(sent) - 1}}

    monkeypatch.setattr(tc, "dispatch_jarvis_response", _fake_jarvis_response)

    # --- run the full chain ---
    r = handle_p0_76_ack(
        bot=bot,
        orchestrator=orch,
        update=_owner_update(42, ACK_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_ack=True,
    )

    # Chain result: claimed by the real dispatch path, completed DONE.
    assert r.task_found and r.task_id == "task_79406871"
    assert r.worker_claimed is True
    assert r.task_final_status == str(TaskStatus.DONE)
    assert r.ack_sent is True and r.ack_message_id is not None
    assert len(sent) == 1, "exactly one egress ACK"

    # --- persisted truth in the REAL store ---
    rec = store.get("task_79406871")
    assert rec.status == TaskStatus.DONE
    assert rec.fencing_token and rec.fencing_token.startswith("fence_task_79406871_"), (
        "fresh fencing token must be minted by the real governor during dispatch"
    )
    # ACK message_id persisted back into the task record (outcome-linked proof).
    assert rec.evidence.get("p0_76_ack_message_id") == r.ack_message_id
    assert rec.evidence.get("p0_76_inbound_update_id") == 42

    # --- real dev_workers execution proof (M1 T02) ---
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT state, evidence FROM dev_workers WHERE task_id = ?", ("task_79406871",)
    ).fetchone()
    conn.close()
    assert row is not None, "real dev_workers claim/finish row must exist"
    assert row[0] == "done"
    assert row[1], "done row must carry non-empty evidence"

    # --- lease released after verify_and_complete ---
    leases = json.loads((tmp_path / "fullchain_lease.json").read_text(encoding="utf-8"))
    assert "task_79406871" not in leases, "governor lease must be released on completion"

    # --- no duplicate task: store still has exactly the seeded task ---
    all_records = store.list_all() if hasattr(store, "list_all") else None
    if all_records is not None:
        assert [t.task_id for t in all_records] == ["task_79406871"]


def test_no_duplicate_task_created_on_missing_binding(p076_env, monkeypatch):
    """If the bound task is absent, the handler must NOT create a second task."""
    env = p076_env
    # Drop the seeded task
    store = env["orch"].store
    store._records.clear() if hasattr(store, "_records") else None
    # Force the by-key lookup to return None.
    monkeypatch.setattr(store, "get_by_idempotency_key", lambda key: None)
    r = handle_p0_76_ack(
        bot=env["bot"],
        orchestrator=env["orch"],
        update=_owner_update(1, ACK_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_ack=True,
    )
    assert r.task_found is False
    assert r.error == "bound_task_not_found"
    assert "No duplicate task created" in r.response_text
    assert r.worker_claimed is False
