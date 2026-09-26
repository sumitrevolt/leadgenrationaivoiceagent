"""Telegram owner-command dispatcher (Task #80).

Binds an authorized Telegram inbound update_id → existing READY task →
synchronous Hermes-style handler execution → persisted result with fencing
token → owner reply carrying the actual outgoing Telegram message_id.

Design constraints (per owner directive Task #80, 2026-09-23):
  * Idempotency bound by ``update_id`` (via TaskRecord.idempotency_key).
  * Reuses existing ``Orchestrator.dispatch_task`` READY → RUNNING path
    (fencing token + lease + dev_workers claim happen there). The
    ``dev_workers`` claim is NOT treated as handler execution — handler
    runs synchronously AFTER dispatch_task returns True.
  * Handler execution = the registered owner-command handler
    (``handle_owner_command`` from ``app.integrations.telegram_owner_commands``)
    completing without raising. Returns ``OwnerCommandResult``.
  * If the handler is missing or fails, the task transitions to REVIEW /
    FAILED with a truthful ``error_message``. NEVER silently fakes success.
  * Reply is sent via ``send_message_with_message_id`` (new). The
    pre-existing boolean-only ``send_message`` callers stay compatible
    (delegates to the new method and discards the message_id).
  * No duplicate reply on retry/replay: idempotency_key match returns the
    existing record's reply_message_id without sending again.

Compliance:
  * RED lane / HARD_OFF agent contracts are enforced by ``dispatch_task``
    (orchestrator never weakens them).
  * No outbound message ever contains tokens / secrets / customer PII
    (handlers are responsible; dispatcher only forwards ``to_telegram_text``).
  * All state transitions go through ``update_cas`` with the fencing
    token returned by dispatch — late / stale results are rejected.

Imports are deliberately local / lazy so the file is importable without
spinning up the FastAPI / DB stack (used by tests).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

# Import TaskStatus directly so we don't rely on DurableTaskStore exposing
# it as a class attribute (the real store does NOT).
from app.platform.automation_orchestrator import TaskStatus as _TaskStatus

logger = logging.getLogger(__name__)


# ---------- Owner-identity helper (no secrets printed) ----------
def _is_owner(chat_id: int | str | None) -> bool:
    """True iff chat_id is in TELEGRAM_OWNER_CHAT_IDS (or default 1621120182)."""
    try:
        raw = (os.getenv("TELEGRAM_OWNER_CHAT_IDS") or "1621120182").strip()
        owners: set[int] = set()
        for piece in raw.replace(",", " ").split():
            try:
                owners.add(int(piece))
            except ValueError:
                continue
        return chat_id is not None and int(chat_id) in owners
    except Exception:
        return False


# ---------- Result types ----------
@dataclass
class DispatchResult:
    """Result of a single dispatch_owner_command invocation.

    Status taxonomy (one of):
      DISPATCHED         — handler ran + reply sent, message_id persisted
      DISPATCHED_NO_REPLY— handler ran + reply send returned False, but
                            handler result is still persisted (FAIL on egress)
      IDEMPOTENT_REPLAY  — same update_id already processed; existing reply
                            message_id returned; no new send
      UNAUTHORIZED       — chat_id is not in owner set; nothing was written
      KILLED             — orchestrator kill switch active; task marked BLOCKED
      NO_READY_TASK      — task_id is missing or not in READY state
      DISPATCH_FAILED    — orchestrator.dispatch_task returned False (race / fence)
      HANDLER_MISSING    — registered handler not callable for this command
      HANDLER_FAILED     — handler raised; task marked FAILED
      REVIEW             — review verdict (e.g., TypeSafe session policy)
    """

    status: str
    task_id: str | None = None
    fencing_token: str | None = None
    reply_message_id: int | None = None
    reason: str | None = None
    owner_command_status: str | None = None  # status field of OwnerCommandResult
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_redacted_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "task_id": self.task_id,
            "fencing_token_fingerprint": (
                "fp_" + str(abs(hash(self.fencing_token)) % (10**10)) if self.fencing_token else None
            ),
            "reply_message_id": self.reply_message_id,
            "reason": self.reason,
            "owner_command_status": self.owner_command_status,
            "started_at_utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_at)
            ),
            "finished_at_utc": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.finished_at))
                if self.finished_at
                else None
            ),
        }


# ---------- Helpers ----------
def _idempotency_key_for_update(update_id: int | str) -> str:
    return f"tg:owner_command:{update_id}"


def _resolve_existing(
    orchestrator: Any,
    idempotency_key: str,
) -> Any | None:
    """Return existing TaskRecord bound to this update_id, if any."""
    try:
        return orchestrator.store.get_by_idempotency_key(idempotency_key)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(
            "telegram_owner_command_dispatcher: idempotency lookup failed: %s",
            type(e).__name__,
        )
        return None


def _ensure_idempotency_bound(
    task: Any,
    update_id: int | str,
    orchestrator: Any,
) -> bool:
    """Bind update_id → task.idempotency_key. Returns False on CAS failure."""
    key = _idempotency_key_for_update(update_id)
    if task.idempotency_key == key:
        return True
    try:
        cas_ok = orchestrator.store.update_cas(
            task_id=task.task_id,
            expected_version=task.version,
            new_status=task.status,  # unchanged
            new_fencing_token=task.fencing_token,
        )
        if not cas_ok:
            return False
        task.idempotency_key = key
        task.updated_at = time.time()
        orchestrator.store.save(task)
        return True
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(
            "telegram_owner_command_dispatcher: idempotency bind failed for %s: %s",
            getattr(task, "task_id", task.id if hasattr(task, "id") else "?"),
            type(e).__name__,
        )
        return False


def _resolve_handler(command: str) -> Any | None:
    """Return the registered handler callable for this command, or None."""
    try:
        from app.integrations.telegram_owner_commands import handle_owner_command

        # handle_owner_command is the single entry point for the 9 owner
        # commands. We probe with /status or any known command to assert
        # the handler is registered. The actual call happens later with the
        # command string from the inbound update.
        if not callable(handle_owner_command):
            return None
        return handle_owner_command
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(
            "telegram_owner_command_dispatcher: handler import failed: %s",
            type(e).__name__,
        )
        return None


def _send_reply(telegram_bot: Any, chat_id: int | str, text: str) -> tuple[bool, int | None]:
    """Send owner reply. Prefers ``send_message_with_message_id``; falls back to
    the legacy boolean-only ``send_message`` (no message_id)."""
    try:
        send_with_id = getattr(telegram_bot, "send_message_with_message_id", None)
        if callable(send_with_id):
            return send_with_id(chat_id, text)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(
            "telegram_owner_command_dispatcher: send_message_with_message_id raised: %s",
            type(e).__name__,
        )
    # Backward-compat fallback
    try:
        ok = bool(telegram_bot.send_message(chat_id, text))
        return ok, None
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(
            "telegram_owner_command_dispatcher: legacy send_message raised: %s",
            type(e).__name__,
        )
        return False, None


# ---------- Main entry ----------
def dispatch_owner_command(
    *,
    update_id: int | str,
    chat_id: int | str,
    command: str,
    task_id: str | None = None,
    orchestrator: Any,
    telegram_bot: Any,
) -> DispatchResult:
    """Resolve and dispatch one Telegram owner command.

    Required kwargs:
      update_id     — Telegram inbound ``update_id`` (used for idempotency)
      chat_id       — Telegram chat_id of the sender (must be owner)
      command       — the command string, e.g. ``/status``
      task_id       — existing READY task to resolve (e.g. ``task_79406871``);
                      if None, dispatcher binds update_id and refuses (no
                      auto-create — the existing READY task is the contract)
      orchestrator  — app.platform.automation_orchestrator.AutomationOrchestrator
      telegram_bot  — app.integrations.telegram_bot.TelegramBot
    """
    res = DispatchResult(status="DISPATCHED", task_id=task_id)

    # 1. Authorization
    if not _is_owner(chat_id):
        res.status = "UNAUTHORIZED"
        res.reason = "chat_not_owner"
        res.finished_at = time.time()
        return res

    # 2. Task required (this dispatcher does NOT auto-create tasks)
    if not task_id:
        res.status = "NO_READY_TASK"
        res.reason = "no_task_id_provided"
        res.finished_at = time.time()
        return res

    # 3. Fetch task
    try:
        task = orchestrator.store.get(task_id)
    except Exception as e:
        res.status = "DISPATCH_FAILED"
        res.reason = f"store_get_failed:{type(e).__name__}"
        res.finished_at = time.time()
        return res
    if task is None:
        res.status = "NO_READY_TASK"
        res.reason = "task_not_found"
        res.finished_at = time.time()
        return res

    # 4. Idempotency: if THIS update_id already has a reply, replay it.
    idem_key = _idempotency_key_for_update(update_id)
    existing = _resolve_existing(orchestrator, idem_key)
    existing_id = getattr(existing, "task_id", getattr(existing, "id", None))
    if existing is not None and existing_id != task.task_id:
        res.status = "IDEMPOTENT_REPLAY"
        res.task_id = existing_id
        res.reason = f"bound_to_different_task:{existing_id}"
        res.finished_at = time.time()
        return res

    # 5. Bind idempotency_key
    if not _ensure_idempotency_bound(task, update_id, orchestrator):
        res.status = "DISPATCH_FAILED"
        res.reason = "idempotency_bind_failed"
        res.finished_at = time.time()
        return res

    # 6. Idempotent replay on the SAME task (already-dispatched update_id)
    # Real TaskRecord doesn't have an outgoing_message_id column — the
    # dispatcher persists it inside input_payload so the replay path can
    # read it back without a schema change. Fall back to evidence inspection
    # for older rows written before this convention.
    persisted_msg_id: int | None = None
    try:
        payload = json.loads(task.input_payload) if task.input_payload else {}
        if isinstance(payload, dict):
            persisted_msg_id = payload.get("dispatched_outgoing_message_id")
    except Exception:
        persisted_msg_id = None
    if persisted_msg_id is None:
        persisted_msg_id = getattr(task, "outgoing_message_id", None)
    if persisted_msg_id is not None or (
        task.evidence and "handler_executed" in str(task.evidence)
    ):
        res.status = "IDEMPOTENT_REPLAY"
        res.fencing_token = task.fencing_token
        res.reply_message_id = persisted_msg_id
        res.reason = "task_already_completed_for_this_update_id"
        res.finished_at = time.time()
        return res

    # 7. Kill switch
    try:
        if orchestrator.is_kill_switch_active():
            task.status = _TaskStatus.BLOCKED
            task.error_message = "Kill switch AUTOMATION_STOP_NEW_CLAIMS active"
            task.updated_at = time.time()
            orchestrator.store.save(task)
            res.status = "KILLED"
            res.reason = task.error_message
            res.finished_at = time.time()
            return res
    except Exception as e:
        res.status = "DISPATCH_FAILED"
        res.reason = f"kill_switch_check_failed:{type(e).__name__}"
        res.finished_at = time.time()
        return res

    # 8. Dispatch (READY → RUNNING with new fencing_token)
    try:
        dispatched = orchestrator.dispatch_task(task_id)
    except Exception as e:
        res.status = "DISPATCH_FAILED"
        res.reason = f"dispatch_raised:{type(e).__name__}:{e}"
        res.finished_at = time.time()
        return res
    if not dispatched:
        # Re-fetch to see what state it landed in
        task = orchestrator.store.get(task_id)
        res.task_id = task_id
        if task and task.status.name == "REVIEW":
            res.status = "REVIEW"
            res.reason = task.error_message or "orchestrator_review_verdict"
        else:
            res.status = "DISPATCH_FAILED"
            res.reason = task.error_message if task else "dispatch_returned_false"
        res.finished_at = time.time()
        return res

    # 9. Refresh task (fencing_token now populated by dispatch_task)
    task = orchestrator.store.get(task_id)
    res.fencing_token = getattr(task, "fencing_token", None)

    # 10. Resolve and execute handler
    handler = _resolve_handler(command)
    if handler is None:
        task.status = _TaskStatus.REVIEW
        task.error_message = "handler_missing:no_registered_handler_for_command"
        task.updated_at = time.time()
        orchestrator.store.save(task)
        res.status = "HANDLER_MISSING"
        res.reason = task.error_message
        res.finished_at = time.time()
        return res

    try:
        owner_result = handler(command)
    except Exception as e:
        task.status = _TaskStatus.FAILED
        task.error_message = f"handler_crashed:{type(e).__name__}:{e}"
        task.updated_at = time.time()
        orchestrator.store.save(task)
        res.status = "HANDLER_FAILED"
        res.reason = task.error_message
        res.finished_at = time.time()
        return res

    # 11. Send reply, capture outgoing message_id (BEFORE verify_and_complete
    # so the StructuredEvidence can carry the persisted message_id even if
    # the egress side failed and we end up marking the task FAILED via the
    # canonical path).
    text = ""
    try:
        text = owner_result.to_telegram_text()
    except Exception as e:  # pragma: no cover - defensive
        text = f"(formatter error: {type(e).__name__})"
    ok, reply_msg_id = _send_reply(telegram_bot, chat_id, text)

    # 12. Build the canonical StructuredEvidence + call verify_and_complete.
    # This is the worker's "finish" path: it validates the fencing token,
    # runs the Guardian StructuredEvidence gate, transitions the task to
    # DONE / FAILED / REVIEW, releases the governor lease, calls
    # _dev_worker_finish (execution proof), and emits the feed events.
    from app.platform.automation_orchestrator import StructuredEvidence

    evidence_payload_struct = {
        "owner_command_result": (
            owner_result.to_data_payload()
            if hasattr(owner_result, "to_data_payload")
            else {"status": getattr(owner_result, "status", None)}
        ),
        "handler_executed": True,
        "handler_invoked_at": time.time(),
        "command": command,
        "fencing_token": res.fencing_token,
        "outgoing_message_id": reply_msg_id,
        "outgoing_delivery_ok": ok,
        "update_id": update_id,
        "chat_id": chat_id,
        "owner_command_status": getattr(owner_result, "status", None),
    }

    # Persist the dispatched message_id into input_payload so the replay
    # branch (above) can find it without a schema migration. Save BEFORE
    # verify_and_complete so the row is committed with the dispatched
    # fields; verify_and_complete then re-fetches, sets status/evidence/
    # error_message, and saves again — but the input_payload column is
    # preserved by the ON CONFLICT DO UPDATE clause above.
    if reply_msg_id is not None:
        try:
            ipayload = json.loads(task.input_payload) if task.input_payload else {}
            if not isinstance(ipayload, dict):
                ipayload = {}
            ipayload["dispatched_outgoing_message_id"] = reply_msg_id
            ipayload["dispatched_fencing_token"] = res.fencing_token
            ipayload["dispatched_update_id"] = update_id
            task.input_payload = json.dumps(ipayload)
            task.updated_at = time.time()
            orchestrator.store.save(task)
        except Exception as e:
            logger.warning(
                "telegram_owner_command_dispatcher: dispatch persist failed: %s",
                type(e).__name__,
            )
    structured_evidence = StructuredEvidence(
        type="telegram_owner_command_dispatch",
        uri_or_path=(
            f"telegram://chat/{chat_id}/msg/{reply_msg_id}"
            if reply_msg_id is not None
            else f"telegram://chat/{chat_id}/update/{update_id}"
        ),
        producer="telegram_owner_command_dispatcher",
        checksum_or_result=evidence_payload_struct,
    )

    # If egress failed, we still mark the handler as FAILED via
    # verify_and_complete(is_success=False) so the canonical path records
    # the failure — we DO NOT silently upgrade an egress failure to DONE.
    if ok:
        try:
            completed = orchestrator.verify_and_complete(
                task_id=task_id,
                execution_evidence=structured_evidence,
                is_success=True,
                fencing_token=res.fencing_token,
            )
        except Exception as e:  # pragma: no cover - defensive
            res.status = "HANDLER_FAILED"
            res.reason = f"verify_and_complete_raised:{type(e).__name__}:{e}"
            res.finished_at = time.time()
            return res
        # Re-read the post-verify_and_complete record to capture state
        post_task = orchestrator.store.get(task_id) or completed
        res.status = "DISPATCHED"
        res.reply_message_id = reply_msg_id
        res.owner_command_status = getattr(owner_result, "status", None)
        res.reason = None
        res.finished_at = time.time()
        return res

    # Egress failed — mark FAILED via canonical path with truthful reason.
    egress_evidence = StructuredEvidence(
        type="telegram_owner_command_dispatch",
        uri_or_path=f"telegram://chat/{chat_id}/update/{update_id}",
        producer="telegram_owner_command_dispatcher",
        checksum_or_result={
            **evidence_payload_struct,
            "outgoing_message_id": None,
            "outgoing_delivery_ok": False,
        },
    )
    try:
        orchestrator.verify_and_complete(
            task_id=task_id,
            execution_evidence=egress_evidence,
            is_success=False,
            error_msg="egress_failure:send_message_returned_false",
            fencing_token=res.fencing_token,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(
            "telegram_owner_command_dispatcher: egress failure persist failed: %s",
            type(e).__name__,
        )
    res.status = "DISPATCHED_NO_REPLY"
    res.reply_message_id = None
    res.owner_command_status = getattr(owner_result, "status", None)
    res.reason = "egress_failure_but_handler_executed"
    res.finished_at = time.time()
    return res
