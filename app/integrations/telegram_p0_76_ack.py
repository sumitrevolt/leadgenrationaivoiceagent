"""P0-76 owner-ACK handler — existing-task-bound, fail-closed, no duplicate execution/ACK.

Canonical handoff: admin task #80 (P0-76 code lane) + orchestrator task
``task_79406871`` (idempotency key ``p0-76:guardian:hermes:telegram_owner_command``,
owner_bot=guardian, assigned_agent=hermes).

Design (per P0_76_CODE_HANDOFF.md):
* The ONLY supported inbound trigger is the exact owner text ``P0-76 ACK`` on an
  authorized owner chat. Anything else is NOT handled here (falls through to the
  normal slash-command / intent path).
* The handler binds that inbound update to the EXISTING orchestrator task by
  idempotency key. It NEVER creates a second task.
* Real worker claim/result: a claim goes through the canonical
  ``AutomationOrchestrator.dispatch_task`` path (CAS READY->RUNNING + governor
  lease + ``dev_workers`` claim row). The worker result is persisted via
  ``verify_and_complete`` with a ``StructuredEvidence`` that references REAL
  on-disk evidence artifacts (never a self-attested ``verified=True`` like
  ``/test_handoff``'s tg_verify task).
* Outcome-linked ACK: on success exactly ONE egress ACK is sent through
  ``dispatch_jarvis_response`` and the returned ``message_id`` is captured into
  the task evidence. Repeated ACKs (same update_id, or a new one after
  completion) are no-ops that RETURN the cached evidence/message_id — no
  duplicate execution, no duplicate ACK.
* Failure paths are fail-closed: unauthorized sender -> deny (no claim, no ACK,
  no audit-suppressed result); bound task missing -> error (no duplicate task);
  worker verification failure -> task requeued/FAILED via
  ``verify_and_complete(is_success=False)`` and the outgoing reply reflects the
  failure (never a fake success).
* The VPS poller is never touched: this module performs one-shot ``sendMessage``
  calls only and reads the Redis cross-process dedupe key (best-effort); it never
  issues ``getUpdates``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("p0_76_ack")

P0_76_ACK_TEXT = "P0-76 ACK"
P0_76_IDEMPOTENCY_KEY = "p0-76:guardian:hermes:telegram_owner_command"
P0_76_ORCHESTRATOR_TASK_ID = "task_79406871"
P0_76_ADMIN_TASK_ID = 76
P0_76_OWNER_CHAT_ID = 1621120182

# Default evidence root (relative to repo root). Overridable via env for deploys.
_DEFAULT_EVIDENCE_DIR = os.path.join("AGNES_WORK", "telegram_p0_desktop_support")
# Required evidence artifacts for the worker-execution step.
REQUIRED_EVIDENCE_FILES = (
    "verifier_json_20260923.json",
    "typesafe_call_trace_20260923.json",
    "P0_76_CODE_HANDOFF.md",
)


def is_p0_76_ack(text: str | None) -> bool:
    """Exact normalized match for the P0-76 trigger text."""
    if not text:
        return False
    return text.strip().upper().replace("-", "-") == P0_76_ACK_TEXT


def _evidence_root() -> str:
    return os.getenv("P0_76_EVIDENCE_DIR", _DEFAULT_EVIDENCE_DIR)


@dataclass
class P076Result:
    """Return contract for :func:`handle_p0_76_ack`."""

    handled: bool = True
    authorized: bool = True
    task_found: bool = False
    task_id: str | None = None
    worker_claimed: bool = False
    task_final_status: str | None = None
    deduplicated: bool = False  # replay of the same update_id -> no side effects
    completed_by_state: bool = False  # already DONE with p0-76 evidence -> no new claim/ACK
    ack_sent: bool = False
    ack_message_id: int | None = None
    cached_ack_message_id: int | None = None
    response_text: str = ""
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "extra"}
        d.update(self.extra)
        return d


def _verify_p0_76_evidence() -> tuple[bool, dict[str, Any], str]:
    """Worker-execution step: verify REAL on-disk evidence artifacts.

    Returns (ok, payload, detail). Never fabricates: missing/incoherent
    artifacts => (False, ..., reason) so the caller persists a FAILED result
    and reflects it in the owner reply.
    """
    root = _evidence_root()
    payload: dict[str, Any] = {"evidence_root": root}
    for fname in REQUIRED_EVIDENCE_FILES:
        p = os.path.join(root, fname)
        if not os.path.exists(p):
            return False, payload, f"evidence artifact missing: {fname}"
        payload[f"{fname}:exists"] = True
    # Coherence checks on the two machine-readable artifacts.
    import json

    try:
        v = json.load(open(os.path.join(root, "verifier_json_20260923.json")))
        creds = v.get("credentials") or {}
        if not (creds.get("jarvis") or {}).get("valid"):
            return False, payload, "verifier JSON: jarvis slot not valid"
        payload["verifier_jarvis_valid"] = True
        payload["verifier_groups_wired"] = (v.get("summary") or {}).get("groups_wired") or (
            v.get("groups_wired") or "unknown"
        )
    except Exception as exc:  # noqa: BLE001
        return False, payload, f"verifier JSON unreadable: {exc}"
    try:
        t = json.load(open(os.path.join(root, "typesafe_call_trace_20260923.json")))
        if not t.get("api_call_success"):
            return False, payload, "typesafe trace: api_call_success not True"
        payload["typesafe_resolved_model"] = t.get("resolved_model")
        payload["typesafe_primary_value"] = t.get("primary_value")
    except Exception as exc:  # noqa: BLE001
        return False, payload, f"typesafe trace unreadable: {exc}"
    return True, payload, "ok"


def handle_p0_76_ack(
    *,
    bot: Any,
    orchestrator: Any,
    update: dict[str, Any],
    chat_id: int | str | None = None,
    send_ack: bool = True,
) -> P076Result:
    """Bind an authorized inbound ``P0-76 ACK`` to the existing orchestrator task.

    Steps: authorize -> replay-dedupe -> resolve existing task (never create)
    -> claim via canonical dispatch (dev_workers row) -> verify real evidence
    -> persist result (DONE or FAILED) -> single outcome-linked egress ACK.
    """
    message = update.get("message") or update.get("channel_post") or {}
    update_id = update.get("update_id")
    from_user = message.get("from") or {}
    user_id = from_user.get("id")
    username = from_user.get("username")

    # 1) Authorization (fail-closed): unauthorized sender -> deny, no side effects.
    authorized = bool(bot.is_owner(user_id=user_id, username=username, chat_id=chat_id))
    if not authorized:
        logger.warning(
            "[p0_76] unauthorized sender denied (user_id=%s chat_id=%s) - no task/claim/ACK",
            user_id,
            chat_id,
        )
        return P076Result(
            authorized=False,
            task_found=False,
            response_text=(f"Rejected: `{P0_76_ACK_TEXT}` is owner-gated. Sender not authorized."),
            error="unauthorized",
        )

    # 2) Replay guard: same update_id delivered twice -> no-op with cached state.
    from app.platform import telegram_coordinator as tc

    if update_id is not None and tc.is_duplicate_update(update_id):
        cached = _cached_result_from_store(orchestrator)
        return P076Result(
            deduplicated=True,
            task_found=cached["task_found"],
            task_id=cached["task_id"],
            task_final_status=cached["task_final_status"],
            cached_ack_message_id=cached["ack_message_id"],
            response_text=(
                f"Replay of update {update_id} ignored — no duplicate execution or ACK."
            ),
            error="replay_deduplicated",
        )

    # 3) Resolve the EXISTING bound task by idempotency key. Never create a new one.
    record = orchestrator.store.get_by_idempotency_key(P0_76_IDEMPOTENCY_KEY)
    if record is None:
        return P076Result(
            task_found=False,
            response_text=(
                f"Error: bound task for key `{P0_76_IDEMPOTENCY_KEY}` not found "
                f"(expected `{P0_76_ORCHESTRATOR_TASK_ID}`). No duplicate task created."
            ),
            error="bound_task_not_found",
        )
    task_id = record.task_id

    # 4) Already completed with P0-76 evidence -> return cached, no new claim/ACK.
    existing_ack_id = _extract_p0_76_ack_message_id(record)
    if existing_ack_id is not None:
        return P076Result(
            task_found=True,
            task_id=task_id,
            task_final_status=str(record.status),
            completed_by_state=True,
            cached_ack_message_id=existing_ack_id,
            response_text=(
                f"`{P0_76_ACK_TEXT}` already completed for task `{task_id}` "
                f"(ACK message_id={existing_ack_id}). No duplicate execution/ACK."
            ),
        )

    # 5) Claim via canonical dispatch path (writes the dev_workers claim row).
    # NOTE: TaskStatus values are UPPERCASE ("READY"/"RUNNING"/...).
    worker_claimed = False
    if record.status.value == "READY":
        dispatch_ok = orchestrator.dispatch_task(task_id)
        worker_claimed = dispatch_ok
        if not dispatch_ok:
            # Task may have been routed to REVIEW by the TypeSafe session
            # policy or blocked by the kill switch — report honestly, no fake success.
            after = orchestrator.store.get(task_id)
            return P076Result(
                task_found=True,
                task_id=task_id,
                worker_claimed=False,
                task_final_status=str(after.status) if after else None,
                response_text=(
                    f"`{P0_76_ACK_TEXT}`: claim blocked — task `{task_id}` is now "
                    f"`{str(after.status) if after else 'UNKNOWN'}` "
                    f"(owner review / kill switch / concurrency). No execution."
                ),
                error="claim_blocked",
            )
    elif record.status.value == "RUNNING":
        worker_claimed = True  # already claimed by a live worker
    else:
        # REVIEW/BLOCKED/FAILED/etc. — do not force a new execution.
        return P076Result(
            task_found=True,
            task_id=task_id,
            task_final_status=str(record.status),
            response_text=(
                f"`{P0_76_ACK_TEXT}`: task `{task_id}` in non-claimable state "
                f"`{record.status}` — no execution attempted."
            ),
            error="task_not_claimable",
        )

    # 6) Worker execution: verify the REAL on-disk P0-76 evidence artifacts.
    ok, payload, detail = _verify_p0_76_evidence()
    payload["inbound_update_id"] = update_id
    payload["bound_orchestrator_task"] = task_id

    # 7) Persist the outcome via the canonical verify/complete path.
    from app.platform.automation_orchestrator import StructuredEvidence, TaskStatus

    if ok:
        evidence = StructuredEvidence(
            type="p0_76_execution_evidence",
            uri_or_path=f"data/orchestrator_ledger.db#task_records:{task_id}",
            producer="hermes",
            checksum_or_result=payload,
        )
        completed = orchestrator.verify_and_complete(
            task_id,
            execution_evidence=evidence,
            is_success=True,
            fencing_token=record.fencing_token,
        )
        ack_sent = False
        ack_message_id: int | None = None
        if completed.status == TaskStatus.DONE and send_ack:
            ack_text = (
                f"P0-76 confirmed: task `{task_id}` worker result verified & completed "
                f"(admin task #76 closed-loop pending owner read). "
                f"outgoing evidence_id=done. ACK delivered."
            )
            api = tc.dispatch_jarvis_response(chat_id, ack_text, parse_mode="HTML")
            if api.get("ok"):
                ack_message_id = (api.get("result") or {}).get("message_id")
                ack_sent = ack_message_id is not None
                # Persist the outgoing message_id back into the task evidence.
                try:
                    rec_now = orchestrator.store.get(task_id)
                    if rec_now is not None:
                        ev = dict(rec_now.evidence or {})
                        ev["p0_76_ack_message_id"] = ack_message_id
                        ev["p0_76_inbound_update_id"] = update_id
                        rec_now.evidence = ev
                        orchestrator.store.save(rec_now)
                except Exception:  # pragma: no cover - defensive
                    pass
        return P076Result(
            task_found=True,
            task_id=task_id,
            worker_claimed=worker_claimed,
            task_final_status=str(completed.status),
            ack_sent=ack_sent,
            ack_message_id=ack_message_id,
            response_text=(
                f"`{P0_76_ACK_TEXT}`: worker result verified — task `{task_id}` "
                f"-> {completed.status}. "
                + (
                    f"ACK sent (message_id={ack_message_id})."
                    if ack_sent
                    else "ACK egress not delivered (see coordinator egress log)."
                )
            ),
        )

    # Failure path: persist FAILED/requeue + reflect the failure, never fake success.
    evidence_fail = StructuredEvidence(
        type="p0_76_execution_failure",
        uri_or_path=f"data/orchestrator_ledger.db#task_records:{task_id}",
        producer="hermes",
        checksum_or_result={"detail": detail, "payload": payload},
    )
    updated = orchestrator.verify_and_complete(
        task_id,
        execution_evidence=evidence_fail,
        is_success=False,
        error_msg=detail,
        fencing_token=record.fencing_token,
    )
    return P076Result(
        task_found=True,
        task_id=task_id,
        worker_claimed=worker_claimed,
        task_final_status=str(updated.status),
        ack_sent=False,
        response_text=(
            f"`{P0_76_ACK_TEXT}` FAILED (fail-closed): {detail}. "
            f"Task `{task_id}` -> {updated.status} (retry/FAILED), "
            f"outgoing reply reflects the failure."
        ),
        error="worker_verification_failed",
    )


def _cached_result_from_store(orchestrator: Any) -> dict[str, Any]:
    rec = orchestrator.store.get_by_idempotency_key(P0_76_IDEMPOTENCY_KEY)
    return {
        "task_found": rec is not None,
        "task_id": rec.task_id if rec else None,
        "task_final_status": str(rec.status) if rec else None,
        "ack_message_id": _extract_p0_76_ack_message_id(rec) if rec else None,
    }


def _extract_p0_76_ack_message_id(record: Any) -> int | None:
    if record is None or not isinstance(record.evidence, dict):
        return None
    val = record.evidence.get("p0_76_ack_message_id")
    return int(val) if isinstance(val, int) else None


__all__ = [
    "P076Result",
    "P0_76_ACK_TEXT",
    "P0_76_IDEMPOTENCY_KEY",
    "P0_76_ORCHESTRATOR_TASK_ID",
    "P0_76_ADMIN_TASK_ID",
    "P0_76_OWNER_CHAT_ID",
    "handle_p0_76_ack",
    "is_p0_76_ack",
]
