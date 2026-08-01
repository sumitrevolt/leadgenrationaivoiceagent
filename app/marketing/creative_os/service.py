"""Creative Automation OS orchestration — API enqueues; Celery video worker renders."""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any

from app.marketing.creative_os import flags
from app.marketing.creative_os.approval import bind_approval, can_publish_to_postiz
from app.marketing.creative_os.assets import get_asset, register_asset, sha256_file
from app.marketing.creative_os.brief import resolve_brief
from app.marketing.creative_os.budget import count_attempts_today, record_attempt
from app.marketing.creative_os.licence import assert_provider_allowed
from app.marketing.creative_os.providers import generate_with_fallback
from app.marketing.creative_os.qa import run_qa
from app.marketing.creative_os.recipes import build_scene_plan, recipe_allowed
from app.marketing.creative_os.spec import CreativeSpec
from app.marketing.creative_os.states import APPROVABLE, CHANGEABLE, assert_transition
from app.marketing.creative_os.store import get_record, list_records, save_record
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Providers that promise a customer-grade animated deliverable. Output from
# these MUST clear `enterprise_qa` before it can reach approval_pending; the
# deterministic provider is deliberately absent because its flat-text render is
# a legitimate internal draft, not a regression.
ENTERPRISE_DELIVERABLE_PROVIDERS = frozenset({"hyperframes"})


def list_cockpit(tenant_id: str = "", limit: int = 50) -> dict[str, Any]:
    if not flags.os_enabled():
        return {
            "ok": True,
            "enabled": False,
            "items": [],
            "counts": {},
            "flags": flags.flag_snapshot(),
            "note": "CREATIVE_OS_ENABLED off",
        }
    out = list_records(tenant_id, limit=limit)
    out["enabled"] = True
    out["flags"] = flags.flag_snapshot()
    return out


def _idem_key(creative_id: str, revision: int) -> str:
    return f"creative_os:{creative_id}:rev{int(revision)}"


def _enqueue_celery(tenant_id: str, creative_id: str, revision: int) -> dict[str, Any]:
    """Dispatch to existing video Celery seam. Never runs FFmpeg in-process."""
    try:
        from app.tasks.video_jobs import render_creative_os_task

        task_id = _idem_key(creative_id, revision)
        async_result = render_creative_os_task.apply_async(
            kwargs={
                "tenant_id": tenant_id,
                "creative_id": creative_id,
                "revision": int(revision),
            },
            task_id=task_id,
        )
        return {"ok": True, "job_id": str(async_result.id), "queue": "video"}
    except Exception as e:
        # Eager / no-broker test path: allow explicit sync worker call only when flagged
        if os.getenv("CREATIVE_OS_EAGER_WORKER", "0").strip() in ("1", "true", "yes"):
            out = process_generation(tenant_id, creative_id)
            return {
                "ok": bool(out.get("ok")),
                "job_id": f"eager-{uuid.uuid4().hex[:10]}",
                "queue": "eager",
                "eager_result": out,
            }
        logger.warning(f"[creative_os] enqueue failed: {e}")
        return {"ok": False, "error": f"enqueue_failed:{str(e)[:120]}"}


def enqueue_generate(
    *,
    tenant_id: str,
    business_name: str,
    recipe: str = "offer_announcement",
    offer: str = "",
    niche: str = "general",
    language: str = "hinglish",
    platform: str = "instagram",
    aspect_ratio: str = "9:16",
    provider: str = "deterministic",
    cta: str = "",
    publish_targets: list[str] | None = None,
    source_asset_ids: list[str] | None = None,
    brand_revision: str = "v1",
    seed: int = 0,
) -> dict[str, Any]:
    """API entry: validate + persist queued CreativeSpec + Celery enqueue. No FFmpeg."""
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}

        # Fail-closed customer brief: entitlement + verified brand facts before any queue write.
        # Missing required fields → NEEDS_CUSTOMER_INPUT (never fabricate a generic video).
        brief_out = resolve_brief(
            tenant_id=tenant_id,
            objective=niche or business_name or "general",
            platform=platform,
            aspect_ratio=aspect_ratio,
            language=language,
            offer=offer,
            cta=cta,
            business_name=business_name,
            niche=niche,
            brand_revision=brand_revision,
        )
        if not brief_out.get("ok"):
            return {
                "ok": False,
                "outcome": brief_out.get("outcome") or "blocked",
                "error": str(brief_out.get("error") or brief_out.get("reason") or "brief_blocked"),
                "reason": brief_out.get("reason"),
                "missing": list(brief_out.get("missing") or []),
            }

        brief = brief_out.get("brief")
        brand = getattr(brief, "brand", None)
        # Bind render copy to verified brief facts — caller overrides cannot inject
        # unverified business_name / niche into on-screen scene text.
        biz_name = str(getattr(brand, "business_name", "") or business_name or "").strip()
        niche_use = str(getattr(brand, "niche", "") or niche or "general").strip()
        offer_use = str(getattr(brief, "offer", "") or offer or "").strip()
        cta_use = str(getattr(brief, "cta", "") or cta or "").strip()
        lang_use = str(getattr(brief, "language", "") or language or "hinglish").strip()

        allow = recipe_allowed(recipe, source_asset_ids=source_asset_ids or [])
        if not allow.get("ok"):
            return allow

        lic = assert_provider_allowed(
            provider, "ffmpeg-template" if provider == "deterministic" else ""
        )
        if provider == "deterministic" and not lic.get("ok"):
            return lic

        used = count_attempts_today(tenant_id)
        if used >= flags.tenant_gen_budget():
            return {
                "ok": False,
                "error": "tenant_budget_exceeded",
                "used": used,
                "budget": flags.tenant_gen_budget(),
            }

        scenes = build_scene_plan(
            recipe,
            business_name=biz_name,
            offer=offer_use,
            niche=niche_use,
            language=lang_use,
            cta=cta_use,
        )
        spec = CreativeSpec(
            creative_id=CreativeSpec.new_id(),
            tenant_id=tenant_id,
            goal=niche_use or "general",
            audience=biz_name,
            offer=offer_use or "",
            language=lang_use,
            platform=platform,
            aspect_ratio=aspect_ratio,
            recipe=recipe,
            brand_revision=brand_revision,
            source_asset_ids=list(source_asset_ids or []),
            script=" | ".join(s.text for s in scenes),
            scenes=scenes,
            captions={"primary": scenes[0].text if scenes else biz_name},
            cta=cta_use or (scenes[-1].text if scenes else ""),
            claims=[],
            provider=provider,
            model_name="ffmpeg-template" if provider == "deterministic" else provider,
            model_version="pinned" if provider == "deterministic" else "unpinned",
            seed=int(seed or 0),
            prompt_version="1",
            licence_snapshot=lic.get("snapshot") or {},
            approval_revision=0,
            publish_targets=list(publish_targets or []),
            status="queued",
        )
        errs = spec.validate()
        if errs:
            return {"ok": False, "error": "spec_invalid", "details": errs}
        spec.compute_input_hashes()

        record_attempt(tenant_id, creative_id=spec.creative_id, kind="initial", revision=0)
        save_record(spec)

        enq = _enqueue_celery(tenant_id, spec.creative_id, 0)
        if not enq.get("ok"):
            spec.status = "failed"
            spec.failure_reason = str(enq.get("error") or "enqueue_failed")
            save_record(spec)
            return {"ok": False, "error": spec.failure_reason, "creative_id": spec.creative_id}

        spec.job_id = str(enq.get("job_id") or "")
        save_record(spec, extra={"job_id": spec.job_id})

        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                tenant_id,
                "creative_os_queued",
                detail=f"{spec.creative_id}:job:{spec.job_id}",
            )
        except Exception:
            pass

        return {
            "ok": True,
            "accepted": True,
            "creative_id": spec.creative_id,
            "job_id": spec.job_id,
            "status": "queued",
            "revision": 0,
            "aspect_ratio": spec.aspect_ratio,
        }
    except Exception as e:
        logger.warning(f"[creative_os] enqueue_generate failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


# Back-compat alias used by older callers/tests
async def generate_preview(**kwargs: Any) -> dict[str, Any]:
    return enqueue_generate(**kwargs)


def process_generation(tenant_id: str, creative_id: str) -> dict[str, Any]:
    """Celery worker entry — heavy render + QA. Never called from web request path."""
    import asyncio

    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        rec = got["record"]
        spec = CreativeSpec.from_dict(rec.get("spec") or {})
        # Idempotent: already terminal success for this revision
        if (
            spec.status == "approval_pending"
            and spec.output_hash
            and (spec.qa_results or {}).get("ok") is True
        ):
            return {"ok": True, "status": spec.status, "idempotent": True}
        if spec.status == "approved":
            return {"ok": True, "status": "approved", "idempotent": True}

        tr = assert_transition(spec.status, "generating")
        if not tr.get("ok") and spec.status not in ("queued", "generating", "changes_requested"):
            # Allow queued/changes_requested→generating; if already generating, continue
            if spec.status != "generating":
                return tr

        if spec.status == "changes_requested":
            tr2 = assert_transition("changes_requested", "queued")
            if not tr2.get("ok"):
                return tr2
            spec.status = "queued"
            save_record(spec)

        if spec.status == "queued":
            tr3 = assert_transition("queued", "generating")
            if not tr3.get("ok"):
                return tr3
        spec.status = "generating"
        save_record(spec)

        timeout = flags.worker_timeout_s()
        t0 = time.time()
        try:
            result = asyncio.run(asyncio.wait_for(generate_with_fallback(spec), timeout=timeout))
        except Exception as e:
            spec.status = "failed"
            spec.failure_reason = (
                "worker_timeout" if "Timeout" in type(e).__name__ else str(e)[:160]
            )
            save_record(spec)
            return {"ok": False, "error": spec.failure_reason, "creative_id": creative_id}

        if spec.fallback_from:
            record_attempt(
                tenant_id,
                creative_id=creative_id,
                kind="fallback",
                revision=int(spec.approval_revision or 0),
            )

        spec.render_duration_ms = int(result.get("timing_ms") or (time.time() - t0) * 1000)
        if not result.get("ok"):
            spec.status = "failed"
            spec.failure_reason = str(result.get("error") or "generate_failed")
            save_record(spec)
            return {
                "ok": False,
                "error": spec.failure_reason,
                "creative_id": creative_id,
            }

        asset0 = (result.get("assets") or [{}])[0]
        path = str(asset0.get("path") or "")
        if not path or not os.path.isfile(path) or not path.lower().endswith(".mp4"):
            spec.status = "failed"
            spec.failure_reason = "output_asset_missing"
            save_record(spec)
            return {"ok": False, "error": "output_asset_missing", "creative_id": creative_id}

        # Path must stay under canonical media roots (reuse customer helper roots)
        if not _path_authorized(path):
            spec.status = "quarantined"
            spec.failure_reason = "path_not_authorized"
            save_record(spec)
            return {"ok": False, "error": "path_not_authorized", "creative_id": creative_id}

        digest = sha256_file(path)
        spec.output_hash = digest
        reg = register_asset(
            tenant_id=tenant_id,
            source_type="generated",
            ref=path,
            sha256=digest,
            mime_type="video/mp4",
            width=int(asset0.get("width") or 0),
            height=int(asset0.get("height") or 0),
            consent_status="granted",
            licence="n/a",
            model_provider=spec.provider,
        )
        if not reg.get("ok"):
            spec.status = "failed"
            spec.failure_reason = "asset_register_failed"
            save_record(spec)
            return {"ok": False, "error": "asset_register_failed", "creative_id": creative_id}
        spec.output_asset_id = str((reg.get("asset") or {}).get("asset_id") or "")

        qa = run_qa(path=path, spec=spec, brand_name=spec.audience)

        # Enterprise deliverable classification. Recorded for EVERY provider so
        # the cockpit can tell a draft from sellable agency work, but only
        # ENFORCED for providers that promise a customer-grade deliverable —
        # enforcing it globally would retroactively fail the deterministic
        # provider's legitimate 720p drafts.
        try:
            from app.marketing.creative_os import enterprise_qa

            grade = enterprise_qa.evaluate(path=path, spec=spec, provider_asset=asset0)
            qa["enterprise"] = grade
            qa["classification"] = grade.get("classification")
        except Exception as e:  # pragma: no cover - defensive, never blocks QA
            logger.warning(f"[creative_os] enterprise grading failed: {e}")
            qa["classification"] = "UNKNOWN"

        spec.qa_results = qa

        if spec.provider in ENTERPRISE_DELIVERABLE_PROVIDERS and not (
            qa.get("enterprise") or {}
        ).get("customer_approvable"):
            grade = qa.get("enterprise") or {}
            spec.status = (
                "quarantined" if grade.get("classification") == "QUARANTINED" else "qa_failed"
            )
            # Carry the base-QA blockers too. This branch returns before the
            # `qa_failed` branch, so without merging them a record that failed
            # BOTH gates would show only the enterprise reason and lose the
            # underlying defect (e.g. black_frame) the cockpit needs to triage.
            reasons = ["enterprise_gate:" + ",".join(grade.get("blockers") or ["unclassified"])]
            if qa.get("ok") is not True and qa.get("blockers"):
                reasons.append("qa:" + ",".join(qa.get("blockers") or []))
            spec.failure_reason = " | ".join(reasons)[:500]
            save_record(spec)
            return {
                "ok": False,
                "error": "enterprise_gate_failed",
                "creative_id": creative_id,
                "classification": grade.get("classification"),
                "qa": qa,
                "status": spec.status,
            }

        if qa.get("ok") is not True:
            trf = assert_transition("generating", "qa_failed")
            if not trf.get("ok"):
                return trf
            spec.status = "qa_failed"
            spec.failure_reason = ",".join(qa.get("blockers") or ["qa_failed"])
            save_record(spec)
            return {
                "ok": False,
                "error": "qa_failed",
                "creative_id": creative_id,
                "qa": qa,
                "status": spec.status,
            }

        tr_ok = assert_transition("generating", "approval_pending")
        if not tr_ok.get("ok"):
            return tr_ok
        spec.status = "approval_pending"
        save_record(spec)
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                tenant_id,
                "creative_os_preview_ready",
                detail=f"{creative_id}:rev{spec.approval_revision}",
            )
        except Exception:
            pass
        return {
            "ok": True,
            "creative_id": creative_id,
            "status": "approval_pending",
            "output_hash": spec.output_hash,
            "output_asset_id": spec.output_asset_id,
            "provider": spec.provider,
            "qa": {"ok": True, "degraded": qa.get("degraded") or []},
        }
    except Exception as e:
        logger.warning(f"[creative_os] process_generation failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def _path_authorized(path: str) -> bool:
    from pathlib import Path

    try:
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_file() or resolved.is_symlink():
            return False
        if resolved.suffix.lower() != ".mp4":
            return False
        roots = [
            Path("data/reels").resolve(),
            Path("data/video_ads").resolve(),
            Path("data/creative_os").resolve(),
        ]
        # Also trust the canonical media roots resolved at CALL time. The literals
        # above are CWD-relative, so in a container where the runtime data dir is
        # redirected (LEADGEN_RUNTIME_DATA_DIR) a perfectly valid render lands
        # outside them and would be wrongly quarantined. These are the same roots
        # the approval snapshot and publish gate use, so trusting them here keeps
        # the two authorities from disagreeing.
        try:
            from app.marketing.video_media_paths import media_roots

            roots.extend(media_roots())
        except Exception:  # pragma: no cover - defensive
            pass
        for root in roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False


def approve_exact(tenant_id: str, creative_id: str, *, actor: str = "admin") -> dict[str, Any]:
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        rec = got["record"]
        status = str(rec.get("status") or "")
        if status == "approved" and rec.get("approval"):
            # Idempotent re-approve same bundle
            return {"ok": True, "approval": rec.get("approval"), "idempotent": True}
        if status not in APPROVABLE:
            return {"ok": False, "error": f"status_blocks_approval:{status}"}
        spec = CreativeSpec.from_dict(rec.get("spec") or {})
        return bind_approval(spec, actor=actor, record=rec)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def request_changes(tenant_id: str, creative_id: str, *, note: str = "") -> dict[str, Any]:
    """Clear approval, bump revision, enqueue regeneration via Celery video queue."""
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        rec = got["record"]
        if str(rec.get("tenant_id") or "") != tenant_id:
            return {"ok": False, "error": "tenant_mismatch"}
        status = str(rec.get("status") or "")
        if status not in CHANGEABLE and status != "approved":
            # Also allow from approved via CHANGEABLE
            if status not in CHANGEABLE:
                return {"ok": False, "error": f"status_blocks_changes:{status}"}

        used = count_attempts_today(tenant_id)
        if used >= flags.tenant_gen_budget():
            return {
                "ok": False,
                "error": "tenant_budget_exceeded",
                "used": used,
                "budget": flags.tenant_gen_budget(),
            }

        spec = CreativeSpec.from_dict(rec.get("spec") or {})
        rev = int(spec.approval_revision or 0)
        if rev + 1 > flags.max_revisions():
            return {
                "ok": False,
                "error": "max_revisions",
                "revision": rev,
                "cap": flags.max_revisions(),
            }

        tr = assert_transition(status, "changes_requested")
        if not tr.get("ok"):
            return tr

        old_approval = rec.get("approval")
        old_hash = spec.output_hash
        spec.previous_output_hash = old_hash
        spec.change_note = (note or "")[:500]
        spec.approval_revision = rev + 1
        spec.output_hash = ""
        spec.output_asset_id = ""
        spec.qa_results = {}
        spec.failure_reason = ""
        spec.status = "changes_requested"
        # Preserve prior approval evidence under history key
        history = list(rec.get("approval_history") or [])
        if old_approval:
            history.append(
                {**old_approval, "invalidated_at": time.time(), "reason": "changes_requested"}
            )
        save_record(
            spec,
            extra={
                "approval": None,
                "approval_history": history,
                "change_note": spec.change_note,
            },
        )

        # Transition to queued + enqueue
        trq = assert_transition("changes_requested", "queued")
        if not trq.get("ok"):
            return trq
        spec.status = "queued"
        save_record(spec, extra={"approval": None, "approval_history": history})

        record_attempt(
            tenant_id,
            creative_id=creative_id,
            kind="regeneration",
            revision=spec.approval_revision,
        )
        enq = _enqueue_celery(tenant_id, creative_id, spec.approval_revision)
        if not enq.get("ok"):
            spec.status = "failed"
            spec.failure_reason = str(enq.get("error") or "enqueue_failed")
            save_record(spec, extra={"approval": None, "approval_history": history})
            return {"ok": False, "error": spec.failure_reason, "creative_id": creative_id}

        spec.job_id = str(enq.get("job_id") or "")
        save_record(
            spec, extra={"approval": None, "job_id": spec.job_id, "approval_history": history}
        )
        return {
            "ok": True,
            "creative_id": creative_id,
            "status": "queued",
            "revision": spec.approval_revision,
            "job_id": spec.job_id,
            "accepted": True,
            "previous_output_hash": old_hash,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def quarantine(tenant_id: str, creative_id: str, *, reason: str = "") -> dict[str, Any]:
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        rec = got["record"]
        status = str(rec.get("status") or "")
        tr = assert_transition(status, "quarantined")
        if not tr.get("ok"):
            return tr
        spec = CreativeSpec.from_dict(rec.get("spec") or {})
        spec.status = "quarantined"
        spec.failure_reason = (reason or "quarantined")[:200]
        return save_record(spec, extra={"approval": None})
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def publish_gate(tenant_id: str, creative_id: str) -> dict[str, Any]:
    return can_publish_to_postiz(tenant_id, creative_id)


def customer_view(tenant_id: str, creative_id: str) -> dict[str, Any]:
    """Customer-safe projection — no paths, providers, or infra."""
    got = get_record(tenant_id, creative_id)
    if not got.get("ok"):
        return got
    rec = got["record"]
    spec = rec.get("spec") or {}
    return {
        "ok": True,
        "creative_id": rec.get("creative_id"),
        "version": rec.get("approval_revision"),
        "status": rec.get("status"),
        "caption": (spec.get("captions") or {}).get("primary", ""),
        "published": rec.get("status") == "published",
        "has_preview": bool(rec.get("output_hash")),
        "delivery_proof": bool(rec.get("approval")),
        "media_url": (
            f"/api/customer/creative-os/{rec.get('creative_id')}/media"
            f"?revision={int(rec.get('approval_revision') or 0)}"
            if rec.get("output_hash")
            else None
        ),
    }


def resolve_output_path(tenant_id: str, creative_id: str) -> dict[str, Any]:
    """Tenant-scoped media path resolve for authenticated serve."""
    got = get_record(tenant_id, creative_id)
    if not got.get("ok"):
        return got
    rec = got["record"]
    spec = CreativeSpec.from_dict(rec.get("spec") or {})
    aid = spec.output_asset_id or ""
    if not aid:
        return {"ok": False, "error": "output_asset_missing"}
    asset = get_asset(tenant_id, aid)
    if not asset.get("ok"):
        return asset
    ref = str((asset.get("asset") or {}).get("ref") or "")
    if not _path_authorized(ref):
        return {"ok": False, "error": "path_not_authorized"}
    return {
        "ok": True,
        "path": ref,
        "sha256": (asset.get("asset") or {}).get("sha256"),
        "revision": spec.approval_revision,
    }


__all__ = [
    "approve_exact",
    "customer_view",
    "enqueue_generate",
    "generate_preview",
    "list_cockpit",
    "process_generation",
    "publish_gate",
    "quarantine",
    "request_changes",
    "resolve_output_path",
]
