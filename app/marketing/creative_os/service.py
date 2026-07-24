"""Creative Automation OS orchestration — vertical slice over video_pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any

from app.marketing.creative_os import flags
from app.marketing.creative_os.approval import (
    bind_approval,
    can_publish_to_postiz,
    invalidate_on_mutation,
)
from app.marketing.creative_os.assets import register_asset, sha256_file
from app.marketing.creative_os.licence import assert_provider_allowed
from app.marketing.creative_os.providers import generate_with_fallback
from app.marketing.creative_os.qa import run_qa
from app.marketing.creative_os.recipes import build_scene_plan, recipe_allowed
from app.marketing.creative_os.spec import CreativeSpec
from app.marketing.creative_os.store import (
    budget_count_today,
    get_record,
    list_records,
    save_record,
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


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


async def generate_preview(
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
    """Queue → generate → QA → approval_pending. Never raises."""
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}

        allow = recipe_allowed(recipe, source_asset_ids=source_asset_ids or [])
        if not allow.get("ok"):
            return allow

        lic = assert_provider_allowed(
            provider, "ffmpeg-template" if provider == "deterministic" else ""
        )
        if provider == "deterministic" and not lic.get("ok"):
            return lic
        if provider != "deterministic":
            # Non-deterministic providers are skeletons — still allow attempt (fail-closed)
            pass

        used = budget_count_today(tenant_id)
        if used >= flags.tenant_gen_budget():
            return {
                "ok": False,
                "error": "tenant_budget_exceeded",
                "used": used,
                "budget": flags.tenant_gen_budget(),
            }

        scenes = build_scene_plan(
            recipe,
            business_name=business_name,
            offer=offer,
            niche=niche,
            language=language,
            cta=cta,
        )
        spec = CreativeSpec(
            creative_id=CreativeSpec.new_id(),
            tenant_id=tenant_id,
            goal=niche or "general",
            audience=business_name,
            offer=offer or "",
            language=language,
            platform=platform,
            aspect_ratio=aspect_ratio,
            recipe=recipe,
            brand_revision=brand_revision,
            source_asset_ids=list(source_asset_ids or []),
            script=" | ".join(s.text for s in scenes),
            scenes=scenes,
            captions={"primary": scenes[0].text if scenes else business_name},
            cta=cta or (scenes[-1].text if scenes else ""),
            claims=[],
            provider=provider,
            model_name="ffmpeg-template" if provider == "deterministic" else provider,
            model_version="pinned" if provider == "deterministic" else "unpinned",
            seed=int(seed or 0),
            prompt_version="1",
            licence_snapshot=lic.get("snapshot") or {},
            approval_revision=0,
            publish_targets=list(publish_targets or []),
            status="generating",
        )
        errs = spec.validate()
        if errs:
            return {"ok": False, "error": "spec_invalid", "details": errs}
        spec.compute_input_hashes()
        save_record(spec)

        timeout = flags.worker_timeout_s()
        try:
            result = await asyncio.wait_for(generate_with_fallback(spec), timeout=timeout)
        except asyncio.TimeoutError:
            spec.status = "failed"
            spec.failure_reason = "worker_timeout"
            save_record(spec)
            return {"ok": False, "error": "worker_timeout", "creative_id": spec.creative_id}

        spec.render_duration_ms = int(result.get("timing_ms") or 0)
        if not result.get("ok"):
            # Try explicit deterministic fallback already inside generate_with_fallback
            spec.status = "failed"
            spec.failure_reason = str(result.get("error") or "generate_failed")
            save_record(spec)
            return {
                "ok": False,
                "error": spec.failure_reason,
                "creative_id": spec.creative_id,
                "provider_result": result,
            }

        asset0 = (result.get("assets") or [{}])[0]
        path = str(asset0.get("path") or "")
        if path and os.path.isfile(path):
            try:
                spec.output_hash = sha256_file(path)
            except Exception:
                spec.output_hash = hashlib.sha256(path.encode()).hexdigest()
            register_asset(
                tenant_id=tenant_id,
                source_type="generated",
                ref=path,
                sha256=spec.output_hash,
                mime_type="video/mp4",
                width=int(asset0.get("width") or 0),
                height=int(asset0.get("height") or 0),
                consent_status="granted",
                licence="n/a",
                model_provider=result.get("provider") or provider,
            )

        qa = run_qa(path=path, spec=spec, brand_name=business_name)
        spec.qa_results = qa
        if not qa.get("ok"):
            spec.status = "qa_failed"
            spec.failure_reason = ",".join(qa.get("blockers") or ["qa_failed"])
            save_record(spec)
            return {
                "ok": False,
                "error": "qa_failed",
                "creative_id": spec.creative_id,
                "qa": qa,
                "status": spec.status,
            }

        spec.status = "approval_pending"
        spec.provider = str(result.get("provider") or provider)
        spec.model_name = str(result.get("model") or spec.model_name)
        save_record(spec)

        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                tenant_id,
                "creative_os_preview_ready",
                detail=f"{spec.creative_id}:rev{spec.approval_revision}",
            )
        except Exception:
            pass

        return {
            "ok": True,
            "creative_id": spec.creative_id,
            "status": spec.status,
            "revision": spec.approval_revision,
            "output_hash": spec.output_hash,
            "spec_hash": spec.spec_hash(),
            "aspect_ratio": spec.aspect_ratio,
            "provider": spec.provider,
            "model": spec.model_name,
            "qa": {"ok": True, "degraded": qa.get("degraded") or []},
            "preview": {
                # Customer-safe: no raw path in public payloads from API layer
                "has_media": bool(path),
                "caption": (spec.captions or {}).get("primary", ""),
                "version": spec.approval_revision,
            },
            "warnings": result.get("warnings") or [],
        }
    except Exception as e:
        logger.warning(f"[creative_os] generate_preview failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def approve_exact(tenant_id: str, creative_id: str, *, actor: str = "admin") -> dict[str, Any]:
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        rec = got["record"]
        if rec.get("status") == "qa_failed":
            return {"ok": False, "error": "qa_failed_blocks_approval"}
        spec = CreativeSpec.from_dict(rec.get("spec") or {})
        out = bind_approval(spec, actor=actor)
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def request_changes(tenant_id: str, creative_id: str, *, note: str = "") -> dict[str, Any]:
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        return invalidate_on_mutation(tenant_id, creative_id, note=note)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def quarantine(tenant_id: str, creative_id: str, *, reason: str = "") -> dict[str, Any]:
    try:
        if not flags.os_enabled():
            return {"ok": False, "error": "CREATIVE_OS_ENABLED off"}
        got = get_record(tenant_id, creative_id)
        if not got.get("ok"):
            return got
        spec = CreativeSpec.from_dict(got["record"].get("spec") or {})
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
        # delivery proof placeholder — reuse ledger externally
        "delivery_proof": bool(rec.get("approval")),
    }


__all__ = [
    "approve_exact",
    "customer_view",
    "generate_preview",
    "list_cockpit",
    "publish_gate",
    "quarantine",
    "request_changes",
]
