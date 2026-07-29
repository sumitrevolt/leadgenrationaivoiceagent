"""Fail-closed publish gate — approval must bind to exact video version."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.marketing.video_production import flags, states
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_HASH_CHUNK = 1024 * 1024  # stream HD video; never read_bytes() a whole render


def hash_video_file(video_path: str) -> tuple[str, int]:
    """Streaming SHA-256 + byte size of the artifact. ``("", 0)`` if unverifiable.

    Path trust is NOT decided here — ``video_media_paths.resolve_video_media_file``
    is the single authority for that, shared with the customer serve path.
    """
    from app.marketing.video_media_paths import resolve_video_media_file

    p = resolve_video_media_file(video_path)
    if p is None:
        return "", 0
    try:
        h = hashlib.sha256()
        size = 0
        with open(p, "rb") as fh:
            while chunk := fh.read(_HASH_CHUNK):
                h.update(chunk)
                size += len(chunk)
        return h.hexdigest(), size
    except Exception:
        return "", 0


def evaluate_publish_gate(
    rec: dict[str, Any],
    *,
    observed_sha256: str,
    observed_bytes: int,
) -> dict[str, Any]:
    """PURE decision function — no file I/O, no writes, no queue, no providers.

    Takes the record plus an ALREADY-OBSERVED content identity and returns the
    same decision/reason contract as :func:`assert_can_publish`. Splitting the
    observation out is what lets the shadow matrix evaluate every row
    deterministically without touching the filesystem.

    Deliberately not exposed as an API endpoint or as a bypass on the real
    publishing path — the only production caller is ``assert_can_publish``,
    which supplies a REAL observation.
    """
    try:
        if flags.production_enabled() and not flags.social_publish_enabled():
            return {"ok": False, "error": "VIDEO_SOCIAL_PUBLISH_ENABLED off"}

        if flags.own_brand_enabled():
            from app.marketing.video_production.allowlist import assert_own_brand_allowlist

            allow = assert_own_brand_allowlist(str(rec.get("client_id") or ""))
            if not allow.get("ok"):
                return allow

        ok, reason = states.publish_allowed(rec)
        if not ok:
            return {"ok": False, "error": reason}

        # Exact-version binding: approved_version must match revision when set
        av = rec.get("approved_version")
        if av is not None and int(av) != int(rec.get("revision") or 0):
            return {
                "ok": False,
                "error": "version_mismatch",
                "approved_version": av,
                "current_revision": rec.get("revision"),
            }

        # Editing after approve invalidates — status must still be approved
        if str(rec.get("status") or "") not in ("approved",):
            if str(rec.get("workflow_state") or "") not in (
                states.APPROVED,
                states.SCHEDULED,
            ):
                return {"ok": False, "error": f"status_not_approved:{rec.get('status')}"}

        if rec.get("final_approved") is False:
            return {"ok": False, "error": "final_approved_false"}

        # Content binding. Every check above is a field on a MUTABLE record, so
        # none of them notices a re-render at the same path and revision. This
        # one re-reads the artifact. It is deliberately READ-ONLY: backfilling a
        # missing hash here would bless whatever bytes happen to be on disk now.
        approved_hash = str(rec.get("approved_content_sha256") or "").strip().lower()
        if not approved_hash:
            return {
                "ok": False,
                "error": "approval_hash_missing",
                "remedy": "re-approval required — this approval predates content binding",
            }
        live_hash = str(observed_sha256 or "").strip().lower()
        live_size = int(observed_bytes or 0)
        if not live_hash:
            return {"ok": False, "error": "content_unverifiable"}
        approved_size = rec.get("approved_content_bytes")
        if live_hash != approved_hash or (
            approved_size is not None and int(approved_size) != live_size
        ):
            return {
                "ok": False,
                "error": "content_hash_mismatch",
                "approved_version": rec.get("approved_version"),
            }

        return {
            "ok": True,
            "version": int(rec.get("revision") or 0),
            "content_sha256": live_hash,
            "content_bytes": live_size,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def assert_can_publish(rec: dict[str, Any]) -> dict[str, Any]:
    """REAL gate: observe the artifact (read-only), then evaluate purely.

    The only production entry point. Never raises.
    """
    try:
        live_hash, live_size = hash_video_file(str(rec.get("video_path") or ""))
    except Exception as e:  # pragma: no cover - defensive
        return {"ok": False, "error": str(e)[:160]}
    return evaluate_publish_gate(rec, observed_sha256=live_hash, observed_bytes=live_size)


def mark_version_approved(
    rec_id: str,
    revision: int,
    *,
    video_path: str = "",
    actor: str = "",
) -> None:
    """COMPATIBILITY WRAPPER — delegates to ``video_ad_cycle.record_approval``.

    There is exactly one implementation of approval mutation and it lives in
    ``video_ad_cycle`` (the module that owns ``_update`` and ``_latest``).
    ``video_path`` is compatibility-only. Omitted → the authoritative record's
    path is used. Supplied and canonically equal → allowed. Supplied and
    DIFFERENT → refused (``approval_video_path_mismatch``); silently hashing
    caller-selected bytes instead of record-selected bytes is the whole attack.
    """
    try:
        from app.marketing import video_ad_cycle

        if video_path:
            from app.marketing.video_media_paths import resolve_video_media_file

            rec = (video_ad_cycle._latest() or {}).get(str(rec_id)) or {}
            supplied = resolve_video_media_file(video_path)
            of_record = resolve_video_media_file(str(rec.get("video_path") or ""))
            if supplied is None or of_record is None or supplied != of_record:
                logger.warning(
                    "[video_ad] approval refused — approval_video_path_mismatch (%s)",
                    str(rec_id)[:40],
                )
                return
        video_ad_cycle.record_approval(
            rec_id,
            int(revision),
            actor=str(actor or "") or video_ad_cycle.APPROVAL_ACTOR_ADMIN,
        )
    except Exception:
        pass


__all__ = [
    "assert_can_publish",
    "hash_video_file",
    "mark_version_approved",
]
