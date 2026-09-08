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

    ``actor_subject`` must be a stable internal id. The checks below are a
    TRIPWIRE against a resolver regression, not the trust boundary — a string
    containing no ``@`` can still be untrusted or PII. Trust comes from the fact
    that :mod:`approval_principal` built the value from an authenticated object.
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


def effect_key(txn_id: str, effect_name: str) -> str:
    """Deterministic per-effect idempotency key: SHA-256 over txn + effect.

    Per-effect, not per-transaction: one shared key would let a retry of a
    FAILED effect be skipped because a DIFFERENT effect had already used it.
    """
    payload = json.dumps(
        {"schema": TXN_SCHEMA, "txn": str(txn_id or ""), "effect": str(effect_name or "")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def _safe_update(rec_id: str, **fields: Any) -> bool:
    """Durable record write that never escapes as an unhandled error.

    A store failure must become a CONTROLLED refusal (409), never a generic
    500 — and never a silently-ignored write either, so the caller decides what
    the transaction state should be.
    """
    from app.marketing import video_ad_cycle

    try:
        video_ad_cycle._update(rec_id, **fields)
        return True
    except Exception as exc:
        logger.warning("[saga] record write failed (%s): %s", str(rec_id)[:40], exc)
        return False


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

    txn = str(rec.get("approval_txn") or "")
    client_id = str(approval.get("client_id") or "")
    content = approval.get("content") or {}
    title = str(content.get("title") or content.get("occasion") or "")

    approval_id = str(approval.get("id") or "")

    def _enqueue() -> None:
        from app.marketing import auto_content

        # auto_content dedupes on ``date|type``, which is DATE-BOUNDED: a retry
        # after local-date rollover would produce a SECOND durable row. The
        # approval id is the stable identity, so check it explicitly first.
        # Serialised by the transaction lock; the date|type rule still covers
        # any concurrent writer.
        if approval_id:
            for row in auto_content.list_queue(client_id, limit=500) or []:
                if str(row.get("approval_id") or "") == approval_id:
                    return
        auto_content.enqueue_approved(client_id, content, approval_id)

    def _delivery() -> None:
        from app.marketing import delivery_ledger

        # log_event(key=...) skips when an event with this key already exists
        # for the client — the idempotency lives DOWNSTREAM, so it holds even
        # if our local marker write dies after the ledger write.
        delivery_ledger.log_event(
            client_id,
            "post_approved",
            detail=title,
            key=effect_key(txn, "delivery_ledger"),
        )

    outcomes: dict[str, str] = {}
    failed = False
    for name, fn in (("enqueue", _enqueue), ("delivery_ledger", _delivery)):
        marker = f"approval_effect_{name}"
        if str(rec.get(marker) or "") == EFFECTS_EMITTED:
            outcomes[name] = "already_emitted"
            continue
        try:
            fn()
        except Exception as exc:
            logger.warning("[saga] effect %s failed (%s): %s", name, str(rec_id)[:40], exc)
            # One effect failing must NOT mark any other effect emitted.
            _safe_update(rec_id, **{marker: EFFECTS_FAILED})
            outcomes[name] = "failed"
            failed = True
            continue
        if not _safe_update(rec_id, **{marker: EFFECTS_EMITTED}):
            # Downstream write happened but the marker did not land. A retry
            # re-invokes the effect, and the downstream idempotency key means
            # the durable output stays exactly one.
            outcomes[name] = "emitted_marker_lost"
            failed = True
            continue
        outcomes[name] = "emitted"

    if failed:
        _safe_update(rec_id, approval_effects=EFFECTS_FAILED)
        return {"ok": False, "error": "effects_failed", "retryable": True, "effects": outcomes}

    if not _safe_update(rec_id, approval_effects=EFFECTS_EMITTED):
        return {
            "ok": False,
            "error": "effects_state_write_failed",
            "retryable": True,
            "effects": outcomes,
        }
    return {"ok": True, "already_emitted": False, "effects": outcomes}


def approve(
    *,
    record_id: str,
    expected_revision: int,
    expected_sha256: str,
    principal: Any,
) -> dict[str, Any]:
    """LAYER B — the one coordinated customer approval path.

    Takes a server-created :class:`ApprovalPrincipal`, never a caller-supplied
    actor string: the previous signature let every surface name itself, and
    three of four named themselves ``"admin"``.

    Only step 10 (finalize) touches the customer-visible approved fields, so a
    transaction that dies earlier leaves the record non-approved and the
    publish gate refusing.
    """
    from app.marketing import content_approval, video_ad_cycle
    from app.marketing.video_production.approval_principal import ApprovalPrincipal
    from app.marketing.video_production.snapshot import prepare_snapshot

    # Identity is checked BEFORE the record is even looked up, and long before
    # a snapshot is written: a failed identity must leave no artifact.
    if not isinstance(principal, ApprovalPrincipal):
        return {"ok": False, "error": "approver_identity_unavailable", "status": 401}
    if not principal.can_approve:
        return {"ok": False, "error": "approval_not_permitted", "status": 403}

    rec = (video_ad_cycle._latest() or {}).get(str(record_id)) or {}
    if not rec:
        return {"ok": False, "error": "video_ad_not_found"}
    tenant_id = str(rec.get("client_id") or "")

    # Wrong tenant fails here — before snapshot, before any store write.
    if not tenant_id or principal.tenant_id != tenant_id:
        return {"ok": False, "error": "approval_tenant_mismatch", "status": 403}

    actor_subject = principal.subject_id
    channel = principal.channel.value

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

        # 6. prepared (still NOT approved to any customer-visible surface).
        # If this write fails the transaction never starts: the snapshot is an
        # unreferenced artifact, reused on retry, and nothing is publishable.
        if not _safe_update(
            record_id,
            approval_txn=txn,
            approval_txn_state=TXN_PREPARED,
            approval_snapshot_path=snap["path"],
            approval_snapshot_sha256=snap["sha256"],
            approval_snapshot_bytes=snap["bytes"],
            approval_actor=str(actor_subject)[:64],
            approval_channel=str(channel)[:32],
            approval_principal_type=principal.principal_type.value,
            approval_evidence_type=principal.auth_evidence_type.value,
            approval_evidence_ref=str(principal.evidence_ref or "")[:64],
            approval_prepared_at=video_ad_cycle._now(),
        ):
            return {"ok": False, "error": "prepared_write_failed", "txn_id": txn}

        # 7. decision bytes only — no callbacks, no effects
        decided = content_approval.persist_decision(token, "approved", txn_id=txn)
        if not decided.get("ok"):
            if not _safe_update(
                record_id,
                approval_txn_state=TXN_COMPENSATED,
                approval_failure_reason="decision_write_failed",
            ):
                # Compensation itself could not be written. Leave the record in
                # PREPARED so recovery surfaces it — never guess it away.
                return {"ok": False, "error": "compensation_write_failed", "txn_id": txn}
            return {"ok": False, "error": "decision_write_failed", "txn_id": txn}

        # 8. decision recorded. The decision IS durable now, so a failure here
        # must leave PREPARED for recovery to finalize — not compensate.
        if not _safe_update(record_id, approval_txn_state=TXN_DECISION_RECORDED):
            return {"ok": False, "error": "state_write_failed", "txn_id": txn}

        # 9-10. finalize the canonical video approval
        bound = video_ad_cycle.record_approval(
            str(record_id), int(expected_revision), actor=str(actor_subject)
        )
        if not bound.get("ok"):
            if not _safe_update(
                record_id,
                approval_txn_state=TXN_COMPENSATED,
                approval_failure_reason=str(bound.get("error") or "finalize_failed"),
            ):
                return {"ok": False, "error": "compensation_write_failed", "txn_id": txn}
            return {
                "ok": False,
                "error": "finalize_failed",
                "detail": bound.get("error"),
                "txn_id": txn,
            }

        if not _safe_update(
            record_id,
            approval_txn_state=TXN_FINALIZED,
            approval_effects=EFFECTS_PENDING,
            approval_finalized_at=video_ad_cycle._now(),
        ):
            # record_approval already wrote the approved fields but the
            # transaction marker did not land — recovery resolves it.
            return {"ok": False, "error": "finalize_state_write_failed", "txn_id": txn}

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
    """Only a FINALIZED transaction may publish.

    This previously also returned True for a record with no saga state at all,
    on the theory that legacy records were "handled by the existing publish-gate
    checks". They were not: the gate never called this function, and a legacy
    hash-only record passed. An absent transaction is now a refusal, so a
    record that was never coordinated needs re-approval rather than a backfill.
    """
    return str((rec or {}).get("approval_txn_state") or "") == TXN_FINALIZED


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
