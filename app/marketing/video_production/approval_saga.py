"""Stage 3A — compensated approval saga coordinator.

Two JSONL stores (content-approval decisions and video-ad records) cannot be
written atomically. This is a COMPENSATED RECOVERABLE SAGA, not a transaction:
each durable step is recorded so a crash leaves a resumable, non-publishable
state rather than a half-approved one.

Layering (the recursion this replaces is pinned by
tests/test_video_approval_recursion_trace.py):

  A  content_approval.persist_decision   - decision bytes only, no callbacks
  B  this module                         - the one coordinator above both stores
  C  emit_post_finalization_effects      - enqueue/ledger, exactly once, AFTER
                                           finalization

The coordinator never calls ``cell.approve_version``, ``content_approval.approve``,
``_decide`` or ``on_approved`` — anything that could re-enter it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

TXN_SCHEMA = 1

# Internal saga stages. Kept SEPARATE from the customer-visible
# workflow_state/status so a half-finished transaction never looks approved.
TXN_PREPARED = "prepared"
TXN_DECISION_RECORDED = "decision_recorded"
TXN_FINALIZED = "finalized"
TXN_COMPENSATED = "compensated"
TXN_INCONSISTENT = "inconsistent"

EFFECTS_PENDING = "approval_effects_pending"
EFFECTS_EMITTED = "approval_effects_emitted"
EFFECTS_FAILED = "approval_effects_failed"

_SHA256_HEX = 64


def transaction_id(
    *,
    tenant_id: str,
    record_id: str,
    revision: int,
    expected_sha256: str,
    actor_subject: str,
    channel: str,
) -> str:
    """Deterministic ID from VERSIONED CANONICAL JSON.

    Not a delimiter-joined string: ``"a|b"`` and ``"a", "|b"`` would collide,
    and so would any value containing the separator. JSON with sorted keys and
    explicit types has no such ambiguity, and ``schema`` lets the shape evolve
    without silently reusing an old id.

    Every field is validated first — a raw token, phone number, email or
    filesystem path must never reach this function, so callers pass a stable
    internal subject only.
    """
    fields = {
        "schema": TXN_SCHEMA,
        "tenant_id": str(tenant_id or ""),
        "record_id": str(record_id or ""),
        "revision": int(revision),
        "expected_sha256": str(expected_sha256 or "").lower(),
        "actor_subject": str(actor_subject or ""),
        "channel": str(channel or ""),
    }
    for key in ("tenant_id", "record_id", "actor_subject", "channel"):
        if not fields[key]:
            raise ValueError(f"transaction_id: {key} required")
    if len(fields["expected_sha256"]) != _SHA256_HEX:
        raise ValueError("transaction_id: expected_sha256 must be 64-hex")
    if fields["revision"] < 0:
        raise ValueError("transaction_id: revision must be >= 0")
    if "@" in fields["actor_subject"] or "/" in fields["actor_subject"]:
        raise ValueError("transaction_id: actor_subject must be a stable id, not PII")

    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _txn_lock(txn_id: str):
    """Transaction-scoped cross-process lock.

    Held for the whole sequence. The individual stores still take and RELEASE
    their own locks one at a time inside it, so two store locks are never held
    simultaneously and there is no ordering to deadlock on.
    """
    try:
        from filelock import FileLock

        from app.marketing.video_media_paths import approved_media_dir

        root = approved_media_dir() / "_txn"
        root.mkdir(parents=True, exist_ok=True)
        return FileLock(str(root / f"{txn_id[:32]}.lock"), timeout=15)
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def emit_post_finalization_effects(rec_id: str, approval: dict[str, Any]) -> dict[str, Any]:
    """LAYER C — side effects, exactly once, only AFTER finalization.

    These used to run inside ``_decide`` before the video record was finalized,
    so a later failure left an enqueued item for an unapproved video. They are
    idempotent on the record's effects state, so a retry re-emits nothing.
    """
    from app.marketing import video_ad_cycle

    rec = (video_ad_cycle._latest() or {}).get(str(rec_id)) or {}
    if str(rec.get("approval_effects") or "") == EFFECTS_EMITTED:
        return {"ok": True, "already_emitted": True}
    if str(rec.get("approval_txn_state") or "") != TXN_FINALIZED:
        return {"ok": False, "error": "effects_before_finalization"}

    client_id = str(approval.get("client_id") or "")
    content = approval.get("content") or {}
    try:
        from app.marketing import auto_content

        auto_content.enqueue_approved(client_id, content, str(approval.get("id") or ""))

        from app.marketing import delivery_ledger

        title = str(content.get("title") or content.get("occasion") or "")
        delivery_ledger.log_event(client_id, "post_approved", detail=title)
    except Exception as exc:
        logger.warning("[saga] effects failed (%s): %s", str(rec_id)[:40], exc)
        video_ad_cycle._update(rec_id, approval_effects=EFFECTS_FAILED)
        return {"ok": False, "error": "effects_failed", "retryable": True}

    video_ad_cycle._update(rec_id, approval_effects=EFFECTS_EMITTED)
    return {"ok": True, "already_emitted": False}


def approve(
    *,
    record_id: str,
    expected_revision: int,
    expected_sha256: str,
    actor_subject: str,
    channel: str,
) -> dict[str, Any]:
    """LAYER B — the one coordinated customer approval path.

    Only step 10 (finalize) touches the customer-visible approved fields, so a
    transaction that dies earlier leaves the record non-approved and the
    publish gate refusing.
    """
    from app.marketing import content_approval, video_ad_cycle
    from app.marketing.video_production.snapshot import prepare_snapshot

    rec = (video_ad_cycle._latest() or {}).get(str(record_id)) or {}
    if not rec:
        return {"ok": False, "error": "video_ad_not_found"}
    tenant_id = str(rec.get("client_id") or "")

    try:
        txn = transaction_id(
            tenant_id=tenant_id,
            record_id=str(record_id),
            revision=int(expected_revision),
            expected_sha256=str(expected_sha256 or ""),
            actor_subject=str(actor_subject or ""),
            channel=str(channel or ""),
        )
    except ValueError as exc:
        return {"ok": False, "error": "invalid_transaction_identity", "detail": str(exc)}

    with _txn_lock(txn):
        rec = (video_ad_cycle._latest() or {}).get(str(record_id)) or {}
        state = str(rec.get("approval_txn_state") or "")
        existing = str(rec.get("approval_txn") or "")

        # 2. identical transaction already finalized -> idempotent success
        if state == TXN_FINALIZED and existing == txn:
            return {
                "ok": True,
                "already_finalized": True,
                "txn_id": txn,
                "approved_at": rec.get("approved_at"),
            }
        # 3. a DIFFERENT transaction already finalized -> deterministic refusal
        if state == TXN_FINALIZED and existing and existing != txn:
            return {
                "ok": False,
                "error": "approval_transaction_conflict",
                "finalized_txn": existing,
            }
        if state == TXN_INCONSISTENT:
            return {"ok": False, "error": "approval_inconsistent", "txn_id": existing}

        # 4. validate against the authoritative record
        if int(rec.get("revision") or 0) != int(expected_revision):
            return {"ok": False, "error": "version_mismatch"}
        token = str(rec.get("token") or "")
        if not token:
            return {"ok": False, "error": "missing_token"}

        # 4b. ADR-142 reject terminality, checked BEFORE any snapshot work so a
        # terminal ledger never causes an artifact to be written. Approval may
        # not flip a decided ledger; only an identical replay is idempotent.
        ledger = content_approval.get_by_token(token) or {}
        ledger_status = str(ledger.get("status") or "").strip().lower()
        if ledger_status in ("approved", "rejected"):
            if ledger_status != "approved":
                return {
                    "ok": False,
                    "error": "approval_already_decided",
                    "status": ledger_status,
                }
            if str(ledger.get("approval_txn") or "") not in ("", txn):
                return {"ok": False, "error": "approval_transaction_conflict"}

        # 5. prepare (or idempotently reuse) the immutable snapshot
        snap = prepare_snapshot(
            tenant_id=tenant_id,
            record_id=str(record_id),
            revision=int(expected_revision),
            expected_sha256=str(expected_sha256),
            source_path=str(rec.get("video_path") or ""),
        )
        if not snap.get("ok"):
            return {"ok": False, "error": snap.get("error") or "snapshot_failed"}

        # 6. prepared (still NOT approved to any customer-visible surface)
        video_ad_cycle._update(
            record_id,
            approval_txn=txn,
            approval_txn_state=TXN_PREPARED,
            approval_snapshot_path=snap["path"],
            approval_snapshot_sha256=snap["sha256"],
            approval_snapshot_bytes=snap["bytes"],
            approval_actor=str(actor_subject)[:64],
            approval_channel=str(channel)[:32],
            approval_prepared_at=video_ad_cycle._now(),
        )

        # 7. decision bytes only — no callbacks, no effects
        decided = content_approval.persist_decision(token, "approved", txn_id=txn)
        if not decided.get("ok"):
            video_ad_cycle._update(
                record_id,
                approval_txn_state=TXN_COMPENSATED,
                approval_failure_reason="decision_write_failed",
            )
            return {"ok": False, "error": "decision_write_failed", "txn_id": txn}

        # 8. decision recorded
        video_ad_cycle._update(record_id, approval_txn_state=TXN_DECISION_RECORDED)

        # 9-10. finalize the canonical video approval
        bound = video_ad_cycle.record_approval(
            str(record_id), int(expected_revision), actor=str(actor_subject)
        )
        if not bound.get("ok"):
            video_ad_cycle._update(
                record_id,
                approval_txn_state=TXN_COMPENSATED,
                approval_failure_reason=str(bound.get("error") or "finalize_failed"),
            )
            return {
                "ok": False,
                "error": "finalize_failed",
                "detail": bound.get("error"),
                "txn_id": txn,
            }

        video_ad_cycle._update(
            record_id,
            approval_txn_state=TXN_FINALIZED,
            approval_effects=EFFECTS_PENDING,
            approval_finalized_at=video_ad_cycle._now(),
        )

        # 11. effects, exactly once, after finalization
        effects = emit_post_finalization_effects(record_id, decided["approval"])

    return {
        "ok": True,
        "txn_id": txn,
        "snapshot_path": snap["path"],
        "content_sha256": snap["sha256"],
        "effects": effects.get("ok"),
        "effects_retryable": effects.get("retryable", False),
    }


def recover(record_id: str) -> dict[str, Any]:
    """Resume or safely compensate an incomplete transaction. Idempotent.

    Uses the same transaction lock as :func:`approve`. Never publishes and
    never invents an approval — a state it cannot resolve becomes visibly
    ``inconsistent`` for an operator.
    """
    from app.marketing import content_approval, video_ad_cycle

    rec = (video_ad_cycle._latest() or {}).get(str(record_id)) or {}
    if not rec:
        return {"ok": False, "error": "video_ad_not_found"}
    txn = str(rec.get("approval_txn") or "")
    state = str(rec.get("approval_txn_state") or "")
    if not txn or not state:
        return {"ok": True, "action": "nothing_to_recover"}

    with _txn_lock(txn):
        rec = (video_ad_cycle._latest() or {}).get(str(record_id)) or {}
        state = str(rec.get("approval_txn_state") or "")

        if state == TXN_PREPARED:
            # Snapshot exists but no decision: the artifact is unreferenced and
            # harmless. Roll the transaction back rather than guessing intent.
            video_ad_cycle._update(
                record_id,
                approval_txn_state=TXN_COMPENSATED,
                approval_failure_reason="recovered_prepared_without_decision",
            )
            return {"ok": True, "action": "compensated_prepared", "txn_id": txn}

        if state == TXN_DECISION_RECORDED:
            token = str(rec.get("token") or "")
            decided = content_approval.get_by_token(token) or {}
            if str(decided.get("status") or "") != "approved":
                video_ad_cycle._update(
                    record_id,
                    approval_txn_state=TXN_INCONSISTENT,
                    approval_failure_reason="decision_missing_after_record",
                )
                return {"ok": False, "action": "inconsistent", "txn_id": txn}
            bound = video_ad_cycle.record_approval(
                str(record_id),
                int(rec.get("revision") or 0),
                actor=str(rec.get("approval_actor") or "recovery"),
            )
            if not bound.get("ok"):
                video_ad_cycle._update(
                    record_id,
                    approval_txn_state=TXN_INCONSISTENT,
                    approval_failure_reason=str(bound.get("error") or "finalize_failed"),
                )
                return {"ok": False, "action": "inconsistent", "txn_id": txn}
            video_ad_cycle._update(
                record_id,
                approval_txn_state=TXN_FINALIZED,
                approval_effects=EFFECTS_PENDING,
                approval_finalized_at=video_ad_cycle._now(),
            )
            state = TXN_FINALIZED

        if state == TXN_FINALIZED:
            effects = str(rec.get("approval_effects") or "")
            if effects in ("", EFFECTS_PENDING, EFFECTS_FAILED):
                token = str(rec.get("token") or "")
                approval = content_approval.get_by_token(token) or {}
                out = emit_post_finalization_effects(record_id, approval)
                return {"ok": out.get("ok", False), "action": "effects_retried", "txn_id": txn}
            return {"ok": True, "action": "already_complete", "txn_id": txn}

        if state == TXN_COMPENSATED:
            return {"ok": True, "action": "already_compensated", "txn_id": txn}
        return {"ok": False, "action": "inconsistent", "txn_id": txn}


def is_publishable(rec: dict[str, Any]) -> bool:
    """Only a finalized transaction may publish. Records with no saga state at
    all are legacy and handled by the existing publish-gate checks."""
    state = str((rec or {}).get("approval_txn_state") or "")
    return state == "" or state == TXN_FINALIZED


__all__ = [
    "EFFECTS_EMITTED",
    "EFFECTS_FAILED",
    "EFFECTS_PENDING",
    "TXN_COMPENSATED",
    "TXN_DECISION_RECORDED",
    "TXN_FINALIZED",
    "TXN_INCONSISTENT",
    "TXN_PREPARED",
    "TXN_SCHEMA",
    "approve",
    "emit_post_finalization_effects",
    "is_publishable",
    "recover",
    "transaction_id",
]
