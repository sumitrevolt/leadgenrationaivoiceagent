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
    P0_76_IDEMPOTENCY_KEY,
    P0_76_OWNER_CHAT_ID,
    P076Result,
    handle_p0_76_ack,
    is_p0_76_ack,
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


def test_t4_failed_worker(p076_env, tmp_path, monkeypatch):
    """Worker verification fails (evidence missing) -> task FAILED/requeue, outgoing reply
    reflects the failure, no ACK sent, no fake success."""
    env = p076_env
    # Remove a required evidence artifact so _verify_p0_76_evidence fails.
    ev_dir = Path(os.environ["P0_76_EVIDENCE_DIR"])
    (ev_dir / "P0_76_CODE_HANDOFF.md").unlink()

    # Patch the fake verify to reflect the FAILED outcome.
    def _fake_verify_fail(
        task_id, execution_evidence=None, is_success=True, error_msg=None, fencing_token=None
    ):
        env["counts"]["verify"] += 1
        rec = env["orch"].store.get(task_id)
        rec.status = TaskStatus.FAILED if not is_success else TaskStatus.DONE
        rec.error_message = error_msg or ""
        env["orch"].store.save(rec)
        env["dev_workers"].finish(task_id, success=is_success, evidence=error_msg or "")
        return rec

    monkeypatch.setattr(env["orch"], "verify_and_complete", _fake_verify_fail)

    r = handle_p0_76_ack(
        bot=env["bot"],
        orchestrator=env["orch"],
        update=_owner_update(1, ACK_TEXT),
        chat_id=P0_76_OWNER_CHAT_ID,
        send_ack=True,
    )
    assert r.error == "worker_verification_failed"
    assert r.task_final_status in (str(TaskStatus.FAILED), str(TaskStatus.READY))
    assert r.ack_sent is False and r.ack_message_id is None
    assert "FAILED" in r.response_text
    assert len(env["sent"]) == 0, "no ACK on failure"
    # dev_workers got a fail finish
    assert env["dev_workers"].finish.called


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
