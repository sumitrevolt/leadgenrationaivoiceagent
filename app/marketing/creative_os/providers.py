"""Provider contract + registry for Creative Automation OS."""

from __future__ import annotations

import time
from typing import Any, Protocol

from app.marketing.creative_os import flags
from app.marketing.creative_os.licence import assert_provider_allowed
from app.marketing.creative_os.spec import CreativeSpec


def normalized_response(
    *,
    ok: bool,
    provider: str,
    model: str = "",
    model_revision: str = "pinned",
    assets: list[dict[str, Any]] | None = None,
    timing_ms: int = 0,
    cost_units: int = 0,
    warnings: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "provider": provider,
        "model": model,
        "model_revision": model_revision,
        "assets": list(assets or []),
        "timing_ms": int(timing_ms or 0),
        "cost_units": int(cost_units or 0),
        "warnings": list(warnings or []),
        "error": error,
    }


class CreativeProvider(Protocol):
    name: str

    async def generate(self, spec: CreativeSpec) -> dict[str, Any]: ...


class DeterministicProvider:
    """Wraps existing video_pipeline.render_creative_video — first real provider."""

    name = "deterministic"

    async def generate(self, spec: CreativeSpec) -> dict[str, Any]:
        t0 = time.time()
        lic = assert_provider_allowed("deterministic", "ffmpeg-template")
        if not lic.get("ok"):
            return normalized_response(
                ok=False,
                provider=self.name,
                model="ffmpeg-template",
                error=str(lic.get("error") or "licence_blocked"),
                timing_ms=int((time.time() - t0) * 1000),
            )
        if not flags.provider_enabled("deterministic"):
            return normalized_response(
                ok=False,
                provider=self.name,
                model="ffmpeg-template",
                error="provider_unavailable",
                timing_ms=int((time.time() - t0) * 1000),
            )
        from app.marketing import video_pipeline

        slides = [s.text for s in (spec.scenes or [])]
        result = await video_pipeline.render_creative_video(
            recipe=spec.recipe or "generic",
            business_name=spec.audience or spec.tenant_id,
            niche=spec.goal or "general",
            slides=slides,
            offer=spec.offer or "",
            client_id=spec.tenant_id,
            ratio=spec.aspect_ratio or "9:16",
        )
        timing = int((time.time() - t0) * 1000)
        if result.get("error"):
            return normalized_response(
                ok=False,
                provider=self.name,
                model="ffmpeg-template",
                model_revision="pinned",
                timing_ms=timing,
                error=str(result.get("error")),
            )
        asset = {
            "path": result.get("path"),
            "aspect_ratio": result.get("aspect_ratio"),
            "width": result.get("width"),
            "height": result.get("height"),
            "size_kb": result.get("size_kb"),
            "slides": result.get("slides"),
        }
        return normalized_response(
            ok=True,
            provider=self.name,
            model="ffmpeg-template",
            model_revision="pinned",
            assets=[asset],
            timing_ms=timing,
            cost_units=0,
            warnings=[],
            error=None,
        )


class _UnavailableSkeleton:
    """Fail-closed adapter — never downloads weights or makes external calls."""

    name = "skeleton"
    model = "unpinned"

    async def generate(self, spec: CreativeSpec) -> dict[str, Any]:
        return normalized_response(
            ok=False,
            provider=self.name,
            model=self.model,
            model_revision="unpinned",
            error="provider_unavailable",
            warnings=["adapter_skeleton_only_no_weights_no_network"],
        )


class QwenImageProvider(_UnavailableSkeleton):
    name = "qwen_image"
    model = "Qwen-Image"


class FluxSchnellProvider(_UnavailableSkeleton):
    name = "flux_schnell"
    model = "FLUX.1-schnell"

    async def generate(self, spec: CreativeSpec) -> dict[str, Any]:
        # Explicitly reject FLUX.dev family even if somehow requested via model_name
        if "dev" in (spec.model_name or "").lower():
            return normalized_response(
                ok=False,
                provider=self.name,
                model=spec.model_name,
                error="provider_unavailable",
                warnings=["flux_dev_family_rejected"],
            )
        return await super().generate(spec)


class Wan22Provider(_UnavailableSkeleton):
    name = "wan22"
    model = "Wan2.2-TI2V-5B"


class ComfyUIProvider(_UnavailableSkeleton):
    name = "comfyui"
    model = "comfyui-lab"


def _hyperframes_provider() -> Any:
    """Build the provider, degrading to a fail-closed stub if it cannot import.

    This is evaluated at MODULE IMPORT time to populate ``_PROVIDERS``, so an
    exception here would propagate to every importer of this module — and
    `providers` is on the import path of `app.main`. A renderer-side problem must
    disable the provider, never take down the web app. The stub keeps the
    provider contract and refuses every call.
    """
    try:
        from app.marketing.creative_os.hyperframes_provider import HyperFramesProvider

        return HyperFramesProvider()
    except Exception as exc:  # pragma: no cover - import-safety net
        import logging

        logging.getLogger(__name__).warning(
            "[creative_os] hyperframes provider unavailable, using fail-closed stub: %s",
            exc,
        )

        class _HyperFramesUnavailable(_UnavailableSkeleton):
            name = "hyperframes"
            model = "hyperframes-cli"

        return _HyperFramesUnavailable()


# Providers whose failure must NOT silently degrade to the deterministic
# flat-text render. If a customer asked for a professional animated deliverable
# and it failed, handing back the low-quality fallback would let a DRAFT_ONLY
# artifact walk into the approval queue looking like the real thing. The failure
# is surfaced instead, with its evidence intact.
NO_SILENT_FALLBACK = frozenset({"hyperframes"})


_PROVIDERS: dict[str, CreativeProvider] = {
    "deterministic": DeterministicProvider(),
    "hyperframes": _hyperframes_provider(),
    "qwen_image": QwenImageProvider(),
    "flux_schnell": FluxSchnellProvider(),
    "wan22": Wan22Provider(),
    "comfyui": ComfyUIProvider(),
}


def get_provider(name: str) -> CreativeProvider:
    key = (name or "deterministic").strip().lower()
    return _PROVIDERS.get(key) or _PROVIDERS["deterministic"]


async def generate_with_fallback(spec: CreativeSpec) -> dict[str, Any]:
    """Try requested provider; on failure fall back to deterministic when OS enabled.

    On successful fallback, mutate ``spec`` to the provider that actually rendered
    BEFORE callers run QA / licence checks.
    """
    requested = (spec.provider or "deterministic").strip().lower()
    primary = get_provider(requested)
    out = await primary.generate(spec)
    if out.get("ok"):
        return out
    if requested in NO_SILENT_FALLBACK:
        # Preserve the failure evidence and stop. Callers classify this as
        # failed / needs-customer-input; nothing reaches approval or Postiz.
        warns = list(out.get("warnings") or [])
        warns.append(f"no_silent_fallback:{requested}")
        out["warnings"] = warns
        out["fallback_suppressed"] = True
        return out
    if requested != "deterministic" and flags.os_enabled():
        fb = await _PROVIDERS["deterministic"].generate(spec)
        if fb.get("ok"):
            from app.marketing.creative_os.licence import assert_provider_allowed

            lic = assert_provider_allowed("deterministic", "ffmpeg-template")
            spec.fallback_from = requested
            spec.provider = "deterministic"
            spec.model_name = "ffmpeg-template"
            spec.model_version = "pinned"
            spec.licence_snapshot = lic.get("snapshot") or {}
            warns = list(fb.get("warnings") or [])
            warns.append(f"fell_back_from:{requested}:{out.get('error')}")
            spec.provider_warnings = warns
            fb["warnings"] = warns
            fb["fallback_from"] = requested
            fb["provider"] = "deterministic"
            fb["model"] = "ffmpeg-template"
            fb["model_revision"] = "pinned"
            return fb
        return out
    return out


__all__ = [
    "ComfyUIProvider",
    "DeterministicProvider",
    "FluxSchnellProvider",
    "QwenImageProvider",
    "Wan22Provider",
    "generate_with_fallback",
    "get_provider",
    "normalized_response",
]
