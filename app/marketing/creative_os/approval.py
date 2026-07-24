"""Exact-hash approval binding for Creative Automation OS."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.marketing.creative_os import flags
from app.marketing.creative_os.spec import CreativeSpec
from app.marketing.creative_os.store import bump_revision, get_record, save_record


def approval_bundle_hash(
    *,
    creative_id: str,
    revision: int,
    spec_hash: str,
    output_hash: str,
    caption_hash: str,
    channel_hash: str,
) -> str:
    payload = "|".join(
        [
            creative_id,
            str(revision),
            spec_hash,
            output_hash,
            caption_hash,
            channel_hash,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bind_approval(spec: CreativeSpec, *, actor: str = "admin") -> dict[str, Any]:
    """Bind approval to exact hashes. Fails if QA not ok or hashes missing."""
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        if not spec.output_hash:
            return {"ok": False, "error": "output_hash_missing"}
        qa = spec.qa_results or {}
        if qa and qa.get("ok") is False:
            return {"ok": False, "error": "qa_failed_blocks_approval"}
        sh = spec.spec_hash()
        ch = spec.caption_hash()
        th = spec.channel_hash()
        rev = int(spec.approval_revision or 0)
        bundle = approval_bundle_hash(
            creative_id=spec.creative_id,
            revision=rev,
            spec_hash=sh,
            output_hash=spec.output_hash,
            caption_hash=ch,
            channel_hash=th,
        )
        approval = {
            "creative_id": spec.creative_id,
            "revision": rev,
            "spec_hash": sh,
            "output_hash": spec.output_hash,
            "caption_hash": ch,
            "channel_hash": th,
            "bundle_hash": bundle,
            "approved_at": time.time(),
            "actor": actor,
            "status": "approved",
        }
        spec.status = "approved"
        rec = save_record(spec, extra={"approval": approval})
        if not rec.get("ok"):
            return rec
        return {"ok": True, "approval": approval}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def assert_exact_approved(creative_id: str, tenant_id: str) -> dict[str, Any]:
    """Publish gate: only exact approved revision may proceed."""
    try:
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        rec = got["record"]
        if rec.get("tenant_id") != tenant_id:
            return {"ok": False, "error": "tenant_mismatch"}
        approval = rec.get("approval") or {}
        if not approval or approval.get("status") != "approved":
            return {"ok": False, "error": "not_approved"}
        try:
            approved_rev = int(approval["revision"])
        except Exception:
            return {"ok": False, "error": "revision_missing"}
        try:
            current_rev = int(
                rec.get("approval_revision") if rec.get("approval_revision") is not None else 0
            )
        except Exception:
            current_rev = 0
        if approved_rev != current_rev:
            return {
                "ok": False,
                "error": "revision_mismatch",
                "approved_revision": approved_rev,
                "current_revision": current_rev,
            }
        # Recompute hashes from stored spec
        spec = CreativeSpec.from_dict(rec.get("spec") or rec)
        if spec.spec_hash() != approval.get("spec_hash"):
            return {"ok": False, "error": "spec_hash_mismatch"}
        if (spec.output_hash or rec.get("output_hash")) != approval.get("output_hash"):
            return {"ok": False, "error": "output_hash_mismatch"}
        if spec.caption_hash() != approval.get("caption_hash"):
            return {"ok": False, "error": "caption_hash_mismatch"}
        if spec.channel_hash() != approval.get("channel_hash"):
            return {"ok": False, "error": "channel_hash_mismatch"}
        expected = approval_bundle_hash(
            creative_id=creative_id,
            revision=int(approval.get("revision") or 0),
            spec_hash=approval["spec_hash"],
            output_hash=approval["output_hash"],
            caption_hash=approval["caption_hash"],
            channel_hash=approval["channel_hash"],
        )
        if expected != approval.get("bundle_hash"):
            return {"ok": False, "error": "bundle_hash_mismatch"}
        return {
            "ok": True,
            "revision": approval.get("revision"),
            "bundle_hash": approval.get("bundle_hash"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def invalidate_on_mutation(
    tenant_id: str,
    creative_id: str,
    *,
    note: str = "",
) -> dict[str, Any]:
    """Any mutation after approval → new revision, approval cleared."""
    try:
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        rec = got["record"]
        rev = int(rec.get("approval_revision") or 0)
        if rev + 1 > flags.max_revisions():
            return {
                "ok": False,
                "error": "max_revisions",
                "revision": rev,
                "cap": flags.max_revisions(),
            }
        return bump_revision(
            tenant_id,
            creative_id,
            note=note,
            clear_approval=True,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def can_publish_to_postiz(tenant_id: str, creative_id: str) -> dict[str, Any]:
    """Combine exact-hash approval with explicit social-publish gate.

    Creative OS is fail-closed: VIDEO_SOCIAL_PUBLISH_ENABLED must be ON.
    Legacy video_ad_cycle behaviour is unchanged when CREATIVE_OS is OFF.
    """
    exact = assert_exact_approved(creative_id, tenant_id)
    if not exact.get("ok"):
        return exact
    if not flags.os_enabled():
        return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
    # Explicit env check — do NOT inherit legacy "production cell OFF ⇒ publish ok"
    import os

    social_on = os.getenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not social_on:
        return {"ok": False, "error": "VIDEO_SOCIAL_PUBLISH_ENABLED off"}
    return {"ok": True, "revision": exact.get("revision"), "publish_ready": True}


__all__ = [
    "approval_bundle_hash",
    "assert_exact_approved",
    "bind_approval",
    "can_publish_to_postiz",
    "invalidate_on_mutation",
]
