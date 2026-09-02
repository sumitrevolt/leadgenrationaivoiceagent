"""Exact-hash approval binding + publish gate with live file SHA verification."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any

from app.marketing.creative_os import flags
from app.marketing.creative_os.assets import get_asset, sha256_file
from app.marketing.creative_os.licence import assert_provider_allowed
from app.marketing.creative_os.spec import CreativeSpec
from app.marketing.creative_os.states import APPROVABLE
from app.marketing.creative_os.store import get_record, save_record


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


def _verify_live_bytes(spec: CreativeSpec) -> dict[str, Any]:
    """Recompute file SHA and compare to spec + asset registry."""
    aid = (spec.output_asset_id or "").strip()
    if not aid:
        return {"ok": False, "error": "output_asset_id_missing"}
    if not (spec.output_hash or "").strip():
        return {"ok": False, "error": "output_hash_missing"}
    got = get_asset(spec.tenant_id, aid)
    if not got.get("ok"):
        return {"ok": False, "error": f"asset_{got.get('error') or 'missing'}"}
    asset = got["asset"]
    if asset.get("revoked") or asset.get("consent_status") in ("denied", "revoked"):
        return {"ok": False, "error": "asset_revoked"}
    if str(asset.get("consent_status") or "") != "granted":
        return {"ok": False, "error": "asset_consent_invalid"}
    ref = str(asset.get("ref") or "")
    if not ref or not os.path.isfile(ref):
        return {"ok": False, "error": "asset_file_missing"}
    try:
        live = sha256_file(ref)
    except Exception as e:
        return {"ok": False, "error": f"hash_failed:{str(e)[:80]}"}
    if live != spec.output_hash:
        return {
            "ok": False,
            "error": "live_hash_mismatch",
            "live": live,
            "expected": spec.output_hash,
        }
    if live != str(asset.get("sha256") or ""):
        return {"ok": False, "error": "asset_registry_hash_mismatch"}
    return {"ok": True, "live_hash": live, "path": ref, "asset": asset}


def bind_approval(
    spec: CreativeSpec,
    *,
    actor: str = "admin",
    record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind approval only when status/QA/asset/licence/live-bytes all pass."""
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        status = (spec.status or "").strip().lower()
        if status not in APPROVABLE:
            return {"ok": False, "error": f"status_blocks_approval:{status}"}

        qa = spec.qa_results or {}
        if not qa or qa.get("ok") is not True:
            return {"ok": False, "error": "qa_missing_or_failed"}

        lic = assert_provider_allowed(spec.provider, spec.model_name, spec.model_version)
        if not lic.get("ok"):
            return {"ok": False, "error": str(lic.get("error") or "licence_blocked")}

        if (spec.model_version or "").strip().lower() in ("", "unpinned", "unknown"):
            if spec.provider == "deterministic":
                pass  # pinned via licence snapshot
            else:
                return {"ok": False, "error": "model_revision_unpinned"}

        live = _verify_live_bytes(spec)
        if not live.get("ok"):
            return live

        sh = spec.spec_hash()
        ch = spec.caption_hash()
        th = spec.channel_hash()
        rev = int(spec.approval_revision if spec.approval_revision is not None else 0)
        bundle = approval_bundle_hash(
            creative_id=spec.creative_id,
            revision=rev,
            spec_hash=sh,
            output_hash=spec.output_hash,
            caption_hash=ch,
            channel_hash=th,
        )

        # Idempotent: same bundle already approved
        if record and record.get("approval"):
            prev = record["approval"]
            if (
                prev.get("status") == "approved"
                and prev.get("bundle_hash") == bundle
                and int(prev.get("revision") if prev.get("revision") is not None else -1) == rev
            ):
                return {"ok": True, "approval": prev, "idempotent": True}
            if prev.get("status") == "approved" and prev.get("bundle_hash") != bundle:
                return {"ok": False, "error": "conflicting_approval"}

        approval = {
            "creative_id": spec.creative_id,
            "revision": rev,
            "spec_hash": sh,
            "output_hash": spec.output_hash,
            "output_asset_id": spec.output_asset_id,
            "caption_hash": ch,
            "channel_hash": th,
            "bundle_hash": bundle,
            "approved_at": time.time(),
            "actor": actor,
            "status": "approved",
            "live_hash": live.get("live_hash"),
        }
        spec.status = "approved"
        rec = save_record(spec, extra={"approval": approval})
        if not rec.get("ok"):
            return rec
        return {"ok": True, "approval": approval}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def assert_exact_approved(creative_id: str, tenant_id: str) -> dict[str, Any]:
    """Publish gate: exact approved revision + live file bytes must still match."""
    try:
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        rec = got["record"]
        if rec.get("tenant_id") != tenant_id:
            return {"ok": False, "error": "tenant_mismatch"}
        if str(rec.get("status") or "") not in ("approved", "scheduled"):
            return {"ok": False, "error": f"status_not_approved:{rec.get('status')}"}
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
            revision=approved_rev,
            spec_hash=approval["spec_hash"],
            output_hash=approval["output_hash"],
            caption_hash=approval["caption_hash"],
            channel_hash=approval["channel_hash"],
        )
        if expected != approval.get("bundle_hash"):
            return {"ok": False, "error": "bundle_hash_mismatch"}

        live = _verify_live_bytes(spec)
        if not live.get("ok"):
            # Quarantine on byte drift
            try:
                from app.marketing.creative_os.states import assert_transition

                tr = assert_transition(str(rec.get("status") or ""), "quarantined")
                if tr.get("ok"):
                    spec.status = "quarantined"
                    spec.failure_reason = str(live.get("error") or "live_hash_mismatch")
                    save_record(spec, extra={"approval": approval})
            except Exception:
                pass
            return live
        if live.get("live_hash") != approval.get("output_hash"):
            return {"ok": False, "error": "approval_live_hash_mismatch"}
        return {
            "ok": True,
            "revision": approved_rev,
            "bundle_hash": approval.get("bundle_hash"),
            "live_hash": live.get("live_hash"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def can_publish_to_postiz(tenant_id: str, creative_id: str) -> dict[str, Any]:
    """Exact approval + live bytes + VIDEO_SOCIAL_PUBLISH_ENABLED explicit ON."""
    exact = assert_exact_approved(creative_id, tenant_id)
    if not exact.get("ok"):
        return exact
    if not flags.os_enabled():
        return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
    social_on = os.getenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not social_on:
        return {"ok": False, "error": "VIDEO_SOCIAL_PUBLISH_ENABLED off"}
    return {
        "ok": True,
        "revision": exact.get("revision"),
        "publish_ready": True,
        "live_hash": exact.get("live_hash"),
    }


__all__ = [
    "approval_bundle_hash",
    "assert_exact_approved",
    "bind_approval",
    "can_publish_to_postiz",
]
