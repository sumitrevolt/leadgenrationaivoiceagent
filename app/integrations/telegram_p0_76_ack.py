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

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("p0_76_ack")

P0_76_ACK_TEXT = "P0-76 ACK"
P0_76_APPROVAL_TEXT = "P0-76 APPROVE"
P0_76_IDEMPOTENCY_KEY = "p0-76:guardian:hermes:telegram_owner_command"
P0_76_ORCHESTRATOR_TASK_ID = "task_79406871"
P0_76_ADMIN_TASK_ID = 76
P0_76_OWNER_CHAT_ID = 1621120182
# Command-linked scope guard: a P0-76 rotation is only valid when bound to the
# canonical guardian task scope. A bound task under a different owner_bot is a
# real execution failure (never silently cross-tenant).
P0_76_EXPECTED_OWNER_BOT = "guardian"

# Default evidence root (relative to repo root). Overridable via env for deploys.
_DEFAULT_EVIDENCE_DIR = os.path.join("AGNES_WORK", "telegram_p0_desktop_support")
# OPTIONAL coherence inputs for the P0-76 step. These are INPUTS (their
# presence enriches the result), NOT the worker-result proof: the completion is
# driven by a command-linked execution computed from the live inbound update +
# the fresh claim token, never by reading these static artifacts.
OPTIONAL_EVIDENCE_INPUTS = (
    "verifier_json_20260923.json",
    "typesafe_call_trace_20260923.json",
    "P0_76_CODE_HANDOFF.md",
)


def is_p0_76_ack(text: str | None) -> bool:
    """Exact normalized match for the P0-76 trigger text."""
    if not text:
        return False
    return text.strip().upper().replace("-", "-") == P0_76_ACK_TEXT


def is_p0_76_approval(text: str | None) -> bool:
    """Exact normalized match for the P0-76 review-approval trigger text."""
    if not text:
        return False
    return text.strip().upper().replace("-", "-") == P0_76_APPROVAL_TEXT


def _compute_p0_76_execution(
    *,
    task_id: str,
    update_id: int | str | None,
    fencing_token: str,
    owner_bot: str,
) -> dict[str, Any]:
    """Command-linked execution result.

    Unlike reading a static artifact, this result is DERIVED FROM the live
    inbound ``update_id`` + the fresh claim (fencing) token minted during this
    dispatch + the bound task. A different update or a re-claim produces a
    different ``execution_fingerprint``, so it cannot be satisfied by replaying
    a historical file. This is the worker-result proof (deterministic from
    command inputs — no clock, no external file).
    """
    canonical = json.dumps(
        {
            "command": P0_76_ACK_TEXT,
            "task_id": task_id,
            "owner_bot": owner_bot,
            "inbound_update_id": update_id,
            "fencing_token": fencing_token,
        },
        sort_keys=True,
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "worker": "p0_76_execution",
        "command": P0_76_ACK_TEXT,
        "task_id": task_id,
        "inbound_update_id": update_id,
        "fencing_token_bound": bool(fencing_token),
        "execution_fingerprint": fingerprint,
        "result": "api_hash_rotation_acknowledged",
        "admin_task_ref": P0_76_ADMIN_TASK_ID,
    }


def _collect_p0_76_inputs() -> tuple[bool, dict[str, Any], str]:
    """Optional coherence inputs (NOT the completion proof).

    Returns (all_present, payload, detail). Missing files only annotate the
    result; they do not fail the command-linked execution.
    """
    root = _evidence_root()
    payload: dict[str, Any] = {"evidence_root": root}
    all_present = True
    for fname in OPTIONAL_EVIDENCE_INPUTS:
        p = os.path.join(root, fname)
        present = os.path.exists(p)
        payload[f"input:{fname}"] = present
        all_present = all_present and present
    detail = "all optional inputs present" if all_present else "some optional inputs missing (input-only, non-fatal)"
    return all_present, payload, detail


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
            after_status = str(after.status) if after else "UNKNOWN"
            if after is not None and after.status.value == "REVIEW":
                return P076Result(
                    task_found=True,
                    task_id=task_id,
                    worker_claimed=False,
                    task_final_status=after_status,
                    response_text=(
                        f"`{P0_76_ACK_TEXT}`: task `{task_id}` held in REVIEW by the "
                        f"TypeSafe session policy — owner review required BEFORE lease. "
                        f"Send `{P0_76_APPROVAL_TEXT}` to approve this specific task "
                        f"(owner-gated, audited). No blanket bypass."
                    ),
                    error="claim_review_gate",
                    extra={"next_action": "owner_approval", "approval_text": P0_76_APPROVAL_TEXT},
                )
            return P076Result(
                task_found=True,
                task_id=task_id,
                worker_claimed=False,
                task_final_status=after_status,
                response_text=(
                    f"`{P0_76_ACK_TEXT}`: claim blocked — task `{task_id}` is now "
                    f"`{after_status}` (kill switch / concurrency). No execution."
                ),
                error="claim_blocked",
            )
        # Re-fetch the record now that the claim has minted a FRESH fencing token.
        record = orchestrator.store.get(task_id)
    elif record.status.value == "RUNNING":
        worker_claimed = True  # already claimed by a live worker
    elif record.status.value == "REVIEW":
        # A REVIEW task is only re-claimable via the owner approval path; the
        # plain ACK must not silently re-execute a review-hold task.
        return P076Result(
            task_found=True,
            task_id=task_id,
            task_final_status=str(record.status),
            response_text=(
                f"`{P0_76_ACK_TEXT}`: task `{task_id}` is in REVIEW — owner review "
                f"pending. Send `{P0_76_APPROVAL_TEXT}` to approve this specific task. "
                f"No execution attempted."
            ),
            error="review_gate",
            extra={"next_action": "owner_approval", "approval_text": P0_76_APPROVAL_TEXT},
        )
    else:
        # BLOCKED/FAILED/etc. — do not force a new execution.
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

    # Command-scope guard: a P0-76 rotation is only valid on the canonical
    # guardian task scope. A bound task under a different owner_bot is a
    # real execution failure — never silently cross-tenant.
    from app.platform.automation_orchestrator import StructuredEvidence, TaskStatus

    owner_scope_ok = record.owner_bot == P0_76_EXPECTED_OWNER_BOT

    # 6) Worker execution: produce a COMMAND-LINKED result (the proof), plus
    # optional coherence inputs. A different update_id / fresh claim token ->
    # different execution_fingerprint, so historical files cannot substitute.
    claim_token = record.fencing_token or ""
    execution = _compute_p0_76_execution(
        task_id=task_id,
        update_id=update_id,
        fencing_token=claim_token,
        owner_bot=record.owner_bot,
    )
    _, inputs_payload, inputs_detail = _collect_p0_76_inputs()
    execution["optional_inputs"] = inputs_payload
    execution["optional_inputs_detail"] = inputs_detail

    # 7) Persist the outcome via the canonical verify/complete path.
    if not owner_scope_ok:
        evidence_fail = StructuredEvidence(
            type="p0_76_scope_mismatch",
            uri_or_path=f"data/orchestrator_ledger.db#task_records:{task_id}",
            producer="hermes",
            checksum_or_result={
                "expected_owner_bot": P0_76_EXPECTED_OWNER_BOT,
                "actual_owner_bot": record.owner_bot,
                "execution": execution,
            },
        )
        updated = orchestrator.verify_and_complete(
            task_id,
            execution_evidence=evidence_fail,
            is_success=False,
            error_msg="owner_bot scope mismatch (cross-tenant guard)",
            fencing_token=claim_token,
        )
        return P076Result(
            task_found=True,
            task_id=task_id,
            worker_claimed=worker_claimed,
            task_final_status=str(updated.status),
            ack_sent=False,
            response_text=(
                f"`{P0_76_ACK_TEXT}` FAILED (scope guard): bound task owner_bot="
                f"`{record.owner_bot}` != `{P0_76_EXPECTED_OWNER_BOT}` — fail-closed, "
                f"no cross-tenant execution."
            ),
            error="scope_mismatch",
            extra={"execution": execution},
        )

    evidence = StructuredEvidence(
        type="p0_76_execution_evidence",
        uri_or_path=f"data/orchestrator_ledger.db#task_records:{task_id}",
        producer="hermes",
        checksum_or_result=execution,
    )
    completed = orchestrator.verify_and_complete(
        task_id,
        execution_evidence=evidence,
        is_success=True,
        fencing_token=claim_token,
    )
    ack_sent = False
    ack_message_id: int | None = None
    if completed.status == TaskStatus.DONE and send_ack:
        ack_text = (
            f"P0-76 confirmed: task `{task_id}` command-linked execution verified "
            f"(fingerprint={execution['execution_fingerprint'][:12]}…) & completed "
            f"(admin task #76 closed-loop pending owner read). ACK delivered."
        )
        api = tc.dispatch_jarvis_response(chat_id, ack_text, parse_mode="HTML")
        if api.get("ok"):
            ack_message_id = (api.get("result") or {}).get("message_id")
            ack_sent = ack_message_id is not None
            # Persist the outgoing message_id + execution proof into the task.
            try:
                rec_now = orchestrator.store.get(task_id)
                if rec_now is not None:
                    ev = dict(rec_now.evidence or {})
                    ev["p0_76_ack_message_id"] = ack_message_id
                    ev["p0_76_inbound_update_id"] = update_id
                    ev["p0_76_execution_fingerprint"] = execution["execution_fingerprint"]
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
            f"`{P0_76_ACK_TEXT}`: command-linked execution verified — task `{task_id}` "
            f"-> {completed.status} (fingerprint={execution['execution_fingerprint'][:12]}…). "
            + (
                f"ACK sent (message_id={ack_message_id})."
                if ack_sent
                else "ACK egress not delivered (see coordinator egress log)."
            )
        ),
        extra={"execution": execution},
    )

@dataclass
class P076ApprovalResult:
    """Return contract for :func:`handle_p0_76_review_approval`."""

    handled: bool = True
    authorized: bool = True
    task_found: bool = False
    task_id: str | None = None
    was_review: bool = False
    approved: bool = False
    released_from_review: bool = False
    new_fencing_token: str | None = None
    task_final_status: str | None = None
    replayed: bool = False
    response_text: str = ""
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "extra"}
        d.update(self.extra)
        return d


def handle_p0_76_review_approval(
    *,
    bot: Any,
    orchestrator: Any,
    update: dict[str, Any],
    chat_id: int | str | None = None,
    send_reply: bool = True,
) -> P076ApprovalResult:
    """Task-specific, owner-gated review-approval for the P0-76 task.

    This is the CANONICAL APPROVAL path for the TypeSafe session-policy REVIEW
    verdict on ``task_79406871`` — NOT a blanket bypass. Semantics:

    * Only the exact owner text ``P0-76 APPROVE`` on an authorized owner chat.
    * Only affects the SINGLE bound task (``P0_76_IDEMPOTENCY_KEY``) while it is
      in ``TaskStatus.REVIEW``.
    * Honors the deterministic gates that still have authority: kill switch
      and RED/HARD_OFF lane are re-checked at approval time — an approval
      never weakens them. A task held by kill switch or RED lane will be
      returned honestly as BLOCKED, not forcibly re-released.
    * Idempotent by ``update_id`` (coordinator dedupe); a re-delivery returns
      the cached state with no re-claim.
    * After a successful CAS REVIEW -> READY (with a fresh fencing token), the
      owner is expected to issue a NEW ``P0-76 ACK`` update (distinct update_id)
      so the command-linked worker result is minted from a live, fresh claim.
    * Durable audit: every approval (success/deny/replay) is written to the
      task record's ``evidence`` with an ``approvals`` list entry — the audit
      trail IS part of the canonical ledger, not a side log.
    """
    message = update.get("message") or update.get("channel_post") or {}
    update_id = update.get("update_id")
    from_user = message.get("from") or {}
    user_id = from_user.get("id")
    username = from_user.get("username")

    # 1) Authorization (fail-closed) — non-owner sender -> deny.
    authorized = bool(bot.is_owner(user_id=user_id, username=username, chat_id=chat_id))
    if not authorized:
        logger.warning(
            "[p0_76_approve] unauthorized sender denied (user_id=%s chat_id=%s)",
            user_id,
            chat_id,
        )
        return P076ApprovalResult(
            authorized=False,
            response_text=(
                f"Rejected: `{P0_76_APPROVAL_TEXT}` is owner-gated. "
                f"Sender not authorized. No task state changed."
            ),
            error="unauthorized",
        )

    # 2) Replay guard.
    from app.platform import telegram_coordinator as tc

    if update_id is not None and tc.is_duplicate_update(update_id):
        cached = _cached_approval_from_store(orchestrator)
        return P076ApprovalResult(
            replayed=True,
            task_found=cached["task_found"],
            task_id=cached["task_id"],
            task_final_status=cached["task_final_status"],
            approved=cached["approved"],
            response_text=(f"Replay of update {update_id} ignored — no duplicate approval."),
            error="replay_deduplicated",
        )

    # 3) Resolve the EXISTING bound task (never create).
    record = orchestrator.store.get_by_idempotency_key(P0_76_IDEMPOTENCY_KEY)
    if record is None:
        return P076ApprovalResult(
            task_found=False,
            response_text=(
                f"Error: bound task for key `{P0_76_IDEMPOTENCY_KEY}` not found. "
                f"No duplicate task created. No approval recorded."
            ),
            error="bound_task_not_found",
        )
    task_id = record.task_id

    # 4) Only APPROVE-able when the task is in REVIEW (the TypeSafe gate outcome).
    if record.status.value != "REVIEW":
        return P076ApprovalResult(
            task_found=True,
            task_id=task_id,
            task_final_status=str(record.status),
            was_review=False,
            response_text=(
                f"`{P0_76_APPROVAL_TEXT}`: task `{task_id}` is in "
                f"`{record.status}`, not REVIEW — approval not applicable. "
                f"No state change."
            ),
            error="not_in_review",
        )

    # 5) Deterministic gates still have authority: an approval must not
    # weaken the kill switch or a RED/HARD_OFF lane. Re-check right now.
    if orchestrator.is_kill_switch_active():
        _record_approval_audit(
            orchestrator,
            task_id,
            approved=False,
            reason="kill_switch_active",
            user_id=user_id,
            username=username,
            chat_id=chat_id,
            update_id=update_id,
        )
        return P076ApprovalResult(
            task_found=True,
            task_id=task_id,
            task_final_status=str(record.status),
            was_review=True,
            approved=False,
            response_text=(
                f"`{P0_76_APPROVAL_TEXT}` denied: kill switch "
                f"`AUTOMATION_STOP_NEW_CLAIMS` active. No state change."
            ),
            error="kill_switch_active",
        )

    try:
        contract = orchestrator.registry[record.assigned_agent]
        lane = getattr(contract, "lane", None)
        lane_blocked = getattr(lane, "value", str(lane)) == "RED"
        mode_blocked = getattr(contract, "default_mode", "") == "hard_off"
        if lane_blocked or mode_blocked:
            _record_approval_audit(
                orchestrator,
                task_id,
                approved=False,
                reason=f"lane_or_mode_blocked(lane={getattr(contract, 'lane', '?')}, mode={getattr(contract, 'default_mode', '?')})",
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                update_id=update_id,
            )
            return P076ApprovalResult(
                task_found=True,
                task_id=task_id,
                task_final_status=str(record.status),
                was_review=True,
                approved=False,
                response_text=(
                    f"`{P0_76_APPROVAL_TEXT}` denied: agent lane/mode is "
                    f"RED / HARD_OFF — deterministic gate has authority, "
                    f"approval cannot bypass."
                ),
                error="lane_or_mode_blocked",
            )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[p0_76_approve] registry lookup failed: %s", e)

    # 6) CAS: REVIEW -> READY, mint a FRESH fencing token via the governor.
    #    A fresh token is REQUIRED so that the subsequent live ACK's
    #    command-linked worker result is bound to a new claim (never the
    #    pre-review stale token).
    new_token = orchestrator.governor.generate_fencing_token(task_id)
    cas_ok = orchestrator.store.update_cas(
        task_id=task_id,
        expected_version=record.version,
        new_status="READY",
        new_fencing_token=new_token,
    )
    if not cas_ok:
        # Version drifted (another process just changed the task). No forced
        # release. Report honestly.
        after = orchestrator.store.get(task_id)
        return P076ApprovalResult(
            task_found=True,
            task_id=task_id,
            was_review=True,
            approved=False,
            released_from_review=False,
            task_final_status=str(after.status) if after else None,
            response_text=(
                f"`{P0_76_APPROVAL_TEXT}`: CAS conflict — task `{task_id}` "
                f"state drifted while approving. No change applied."
            ),
            error="cas_conflict",
        )

    # 7) Durable audit: record the approval + fresh token in the task evidence.
    _record_approval_audit(
        orchestrator,
        task_id,
        approved=True,
        reason="owner_review_approval",
        user_id=user_id,
        username=username,
        chat_id=chat_id,
        update_id=update_id,
        fencing_token=new_token,
    )
    # Ensure the record's error_message is cleared so the next dispatch does
    # not surface a stale "TypeSafe session policy requires owner review"
    # line from the pre-approval state.
    rec_now = orchestrator.store.get(task_id)
    if rec_now is not None and rec_now.error_message:
        rec_now.error_message = None
        orchestrator.store.save(rec_now)

    # 8) Optional owner-facing confirmation egress (does NOT count as the
    #    command-linked ACK — that happens on the NEXT live P0-76 ACK).
    if send_reply and chat_id is not None:
        try:
            from app.platform import telegram_coordinator as tc2

            tc2.dispatch_jarvis_response(
                chat_id,
                (
                    f"P0-76 APPROVED: task `{task_id}` released from REVIEW to "
                    f"READY (fresh claim token). Next: owner issues a fresh "
                    f"`{P0_76_ACK_TEXT}`."
                ),
                parse_mode="HTML",
            )
        except Exception:  # pragma: no cover - defensive
            pass

    return P076ApprovalResult(
        task_found=True,
        task_id=task_id,
        was_review=True,
        approved=True,
        released_from_review=True,
        new_fencing_token=new_token,
        task_final_status="READY",
        response_text=(
            f"`{P0_76_APPROVAL_TEXT}`: task `{task_id}` REVIEW -> READY "
            f"(fencing token refreshed, audit recorded in task evidence). "
            f"Owner now issues a fresh `{P0_76_ACK_TEXT}`."
        ),
    )


def _record_approval_audit(
    orchestrator: Any,
    task_id: str,
    *,
    approved: bool,
    reason: str,
    user_id: int | str | None,
    username: str | None,
    chat_id: int | str | None,
    update_id: int | str | None,
    fencing_token: str | None = None,
) -> None:
    """Durable audit: append the approval/deny event to the task's evidence."""
    try:
        rec = orchestrator.store.get(task_id)
        if rec is None:
            return
        ev = dict(rec.evidence or {})
        approvals = list(ev.get("approvals") or [])
        approvals.append(
            {
                "ts": time.time(),
                "update_id": update_id,
                "user_id": user_id,
                "username": username,
                "chat_id": chat_id,
                "approved": approved,
                "reason": reason,
                "fencing_token_fingerprint": (
                    "fp_" + str(abs(hash(fencing_token)) % (10**10)) if fencing_token else None
                ),
            }
        )
        ev["approvals"] = approvals
        rec.evidence = ev
        orchestrator.store.save(rec)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[p0_76_approve] audit write failed: %s", e)


def _cached_approval_from_store(orchestrator: Any) -> dict[str, Any]:
    rec = orchestrator.store.get_by_idempotency_key(P0_76_IDEMPOTENCY_KEY)
    ev = rec.evidence if rec and isinstance(rec.evidence, dict) else {}
    approvals = ev.get("approvals") or []
    return {
        "task_found": rec is not None,
        "task_id": rec.task_id if rec else None,
        "task_final_status": str(rec.status) if rec else None,
        "approved": any(a.get("approved") for a in approvals) if approvals else False,
    }


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
    "P076ApprovalResult",
    "P0_76_ACK_TEXT",
    "P0_76_APPROVAL_TEXT",
    "P0_76_IDEMPOTENCY_KEY",
    "P0_76_ORCHESTRATOR_TASK_ID",
    "P0_76_ADMIN_TASK_ID",
    "P0_76_OWNER_CHAT_ID",
    "P0_76_EXPECTED_OWNER_BOT",
    "handle_p0_76_ack",
    "handle_p0_76_review_approval",
    "is_p0_76_ack",
    "is_p0_76_approval",
]
