"""Creative provider licence allowlist — software ≠ model-weight clearance."""

from __future__ import annotations

from typing import Any

# Exact allowlist. Unknown provider/checkpoint = blocked.
# commercial_use must be explicitly True for production eligibility.
LICENCE_REGISTRY: dict[str, dict[str, Any]] = {
    "deterministic/ffmpeg-template": {
        "provider": "deterministic",
        "model": "ffmpeg-template",
        "model_revision": "pinned",
        "software_licence": "Apache-2.0",  # LeadGen code path
        "weight_licence": "n/a",  # no ML weights
        "checkpoint": "n/a",
        "commercial_use": True,
        "attribution_required": False,
        "restrictions": "Uses local FFmpeg + Pillow only; no generative weights.",
        "approval_date": "2026-07-24",
        "production_eligible": True,
    },
    "hyperframes/hyperframes-cli": {
        "provider": "hyperframes",
        "model": "hyperframes-cli",
        "model_revision": "0.7.87",
        # Verified 2026-08-01 from the upstream repo's LICENSE via the GitHub API
        # and the published package's own `license` field — both Apache-2.0.
        "software_licence": "Apache-2.0",
        # No ML weights are involved: this is an HTML -> Chrome -> FFmpeg
        # renderer. "n/a" (not "unknown") is what keeps assert_provider_allowed
        # from failing closed on the weight check.
        "weight_licence": "n/a",
        "checkpoint": "n/a",
        "commercial_use": True,
        "attribution_required": False,
        "restrictions": (
            "Local subprocess render only; HeyGen cloud/lambda/cloudrun subcommands "
            "and telemetry are disabled. Fonts are bundled Noto (OFL-1.1). GSAP is "
            "deliberately NOT bundled — its Standard 'no charge' licence is not OSI. "
            "Upstream commit 343c0251 (2026-08-01), npm hyperframes@0.7.87."
        ),
        "approval_date": "2026-08-01",
        "production_eligible": True,
        "rollback_provider": "deterministic",
    },
    "qwen_image/blocked": {
        "provider": "qwen_image",
        "model": "Qwen-Image",
        "model_revision": "unpinned",
        "software_licence": "Apache-2.0",
        "weight_licence": "unknown",
        "checkpoint": "unknown",
        "commercial_use": False,
        "attribution_required": True,
        "restrictions": "Blocked until exact Apache checkpoint + local hardware bench.",
        "approval_date": "",
        "production_eligible": False,
    },
    "flux_schnell/blocked": {
        "provider": "flux_schnell",
        "model": "FLUX.1-schnell",
        "model_revision": "unpinned",
        "software_licence": "Apache-2.0",
        "weight_licence": "unknown",
        "checkpoint": "unknown",
        "commercial_use": False,
        "attribution_required": True,
        "restrictions": "schnell only if commercial-use verified; FLUX.dev family REJECTED.",
        "approval_date": "",
        "production_eligible": False,
    },
    "wan22/blocked": {
        "provider": "wan22",
        "model": "Wan2.2-TI2V-5B",
        "model_revision": "unpinned",
        "software_licence": "unknown",
        "weight_licence": "unknown",
        "checkpoint": "unknown",
        "commercial_use": False,
        "attribution_required": True,
        "restrictions": "GPU worker only; never web container; no prod VPS without preflight.",
        "approval_date": "",
        "production_eligible": False,
    },
    "comfyui/blocked": {
        "provider": "comfyui",
        "model": "comfyui-lab",
        "model_revision": "unpinned",
        "software_licence": "GPL-3.0",
        "weight_licence": "varies",
        "checkpoint": "unknown",
        "commercial_use": False,
        "attribution_required": True,
        "restrictions": "Isolated lab only; custom nodes allowlisted + commit-pinned.",
        "approval_date": "",
        "production_eligible": False,
    },
}

# Hard rejects — never production-eligible in this OS.
_REJECTED_MODELS = frozenset(
    {
        "ltx-2",
        "ltx2",
        "hunyuanvideo",
        "hunyuan-video",
        "flux.dev",
        "flux_dev",
        "flux.1-dev",
        "flux1-dev",
    }
)


def is_rejected_model(model: str) -> bool:
    key = (model or "").strip().lower().replace(" ", "")
    if key in _REJECTED_MODELS:
        return True
    if "flux" in key and "dev" in key:
        return True
    return False


def lookup(provider: str, model: str = "", revision: str = "") -> dict[str, Any] | None:
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    if p == "deterministic":
        return dict(LICENCE_REGISTRY["deterministic/ffmpeg-template"])
    for _key, row in LICENCE_REGISTRY.items():
        if row.get("provider") == p and (not m or row.get("model") == m):
            out = dict(row)
            if revision:
                out["model_revision"] = revision
            return out
    return None


def assert_provider_allowed(provider: str, model: str = "", revision: str = "") -> dict[str, Any]:
    """Fail-closed licence gate. Unknown = blocked."""
    if is_rejected_model(model) or is_rejected_model(f"{provider}/{model}"):
        return {
            "ok": False,
            "error": "licence_rejected_model",
            "provider": provider,
            "model": model,
        }
    row = lookup(provider, model, revision)
    if not row:
        return {
            "ok": False,
            "error": "licence_unknown",
            "provider": provider,
            "model": model,
        }
    if row.get("weight_licence") == "unknown" and provider != "deterministic":
        return {
            "ok": False,
            "error": "licence_weight_unknown",
            "snapshot": row,
        }
    if not row.get("commercial_use"):
        return {
            "ok": False,
            "error": "licence_commercial_blocked",
            "snapshot": row,
        }
    if not row.get("production_eligible"):
        return {
            "ok": False,
            "error": "licence_not_production_eligible",
            "snapshot": row,
        }
    return {"ok": True, "snapshot": row}


__all__ = [
    "LICENCE_REGISTRY",
    "assert_provider_allowed",
    "is_rejected_model",
    "lookup",
]
