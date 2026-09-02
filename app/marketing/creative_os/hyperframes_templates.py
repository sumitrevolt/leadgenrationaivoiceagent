"""Immutable allowlist of HyperFrames render templates.

A template id is the ONLY thing that selects rendering code, so this registry is
the security boundary for "which HTML may Chrome execute". It is a frozen,
in-code allowlist: an id that is not literally a key here can never reach the
renderer, which is what stops a customer-supplied string from pointing the
renderer at arbitrary HTML on disk.

Each entry pins the template's own version so an approved video's identity can
be traced back to the exact composition that produced it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# app/marketing/creative_os/hyperframes_templates.py -> repo root is 3 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]

RENDERER_DIRNAME = os.path.join("video_renderer", "hyperframes")

# Aspect ratio -> HyperFrames --resolution preset. Anything absent is refused
# rather than silently rendered at the wrong shape.
RESOLUTION_PRESETS: dict[str, tuple[str, int, int]] = {
    "9:16": ("portrait", 1080, 1920),
    "1:1": ("square", 1080, 1080),
    "16:9": ("landscape", 1920, 1080),
}

TEMPLATE_REGISTRY: dict[str, dict[str, Any]] = {
    "beauty_luxury_offer_v1": {
        "template_id": "beauty_luxury_offer_v1",
        "template_version": "1.0.0",
        "dir": "templates/beauty_luxury_offer_v1",
        "label": "Beauty / salon premium offer reel",
        "scene_count": 6,
        "duration_s": 25.4,
        "aspect_ratios": ("9:16",),
        "requires_photos": False,
        "animation_runtime": "css",
        # Variables the composition declares. The manifest builder refuses any
        # key outside this set so a typo becomes an error instead of a silently
        # ignored value that renders as a blank slot.
        "variables": (
            "business_name",
            "monogram",
            "tagline",
            "city",
            "primary_color",
            "accent_color",
            "hook_line",
            "hook_sub",
            "services_json",
            "showcase_line",
            "proof_line",
            "offer_title",
            "offer_sub",
            "cta_text",
            "cta_channel",
            "contact_display",
            "photos_json",
            "footer_note",
        ),
        # Without these the render would be off-brand or anonymous, so their
        # absence is NEEDS_CUSTOMER_INPUT rather than a default.
        "required_variables": (
            "business_name",
            "primary_color",
            "accent_color",
            "hook_line",
            "cta_text",
        ),
    },
    "local_service_promo_v1": {
        "template_id": "local_service_promo_v1",
        "template_version": "1.0.0",
        "dir": "templates/local_service_promo_v1",
        "label": "Local SMB service promo (problem → solution → proof → offer → CTA)",
        "scene_count": 6,
        "duration_s": 25.4,
        "aspect_ratios": ("9:16",),
        "requires_photos": False,
        "animation_runtime": "css",
        "variables": (
            "business_name",
            "monogram",
            "tagline",
            "city",
            "primary_color",
            "accent_color",
            "problem_line",
            "problem_strike",
            "solution_line",
            "solution_sub",
            "steps_json",
            "trust_json",
            "proof_line",
            "offer_title",
            "offer_sub",
            "cta_text",
            "cta_channel",
            "contact_display",
            "photos_json",
            "footer_note",
        ),
        "required_variables": (
            "business_name",
            "primary_color",
            "accent_color",
            "problem_line",
            "solution_line",
            "cta_text",
        ),
    },
    "agency_product_launch_v1": {
        "template_id": "agency_product_launch_v1",
        "template_version": "1.0.0",
        "dir": "templates/agency_product_launch_v1",
        "label": "LeadGen AI own-brand product launch reel",
        "scene_count": 6,
        "duration_s": 25.4,
        "aspect_ratios": ("9:16",),
        "requires_photos": False,
        "animation_runtime": "css",
        "variables": (
            "product_name",
            "monogram",
            "tagline",
            "eyebrow",
            "primary_color",
            "accent_color",
            "hook_line",
            "hook_sub",
            "showcase_line",
            "features_json",
            "workflow_json",
            "metrics_json",
            "cta_text",
            "contact_display",
            "photos_json",
            "footer_note",
        ),
        "required_variables": (
            "product_name",
            "primary_color",
            "accent_color",
            "hook_line",
            "cta_text",
        ),
    },
}


def renderer_root() -> Path:
    """Absolute path to the pinned renderer package (repo-anchored, not CWD)."""
    override = os.getenv("CREATIVE_HYPERFRAMES_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return (_REPO_ROOT / RENDERER_DIRNAME).resolve()


def get_template(template_id: str) -> dict[str, Any] | None:
    """Exact-match lookup. Unknown id = None (caller must fail closed)."""
    # Deliberately NOT normalised — no strip(), no lower(), no separator fixing.
    # Normalisation is what lets a hostile or malformed id be *rewritten* into a
    # real one; callers that read from env normalise at their own edge (see
    # `hyperframes_provider.default_template`) so this boundary stays exact.
    row = TEMPLATE_REGISTRY.get(str(template_id or ""))
    return dict(row) if row else None


def template_dir(template_id: str) -> Path | None:
    """Resolved template project directory, or None when not allowlisted.

    Returns None if the resolved directory escapes the renderer root — defence
    in depth behind the allowlist, so a bad registry edit cannot become a path
    traversal.
    """
    row = get_template(template_id)
    if not row:
        return None
    root = renderer_root()
    try:
        resolved = (root / str(row["dir"])).resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        return None
    if not (resolved / "index.html").is_file():
        return None
    return resolved


def list_templates() -> list[dict[str, Any]]:
    return [dict(v) for v in TEMPLATE_REGISTRY.values()]


__all__ = [
    "RESOLUTION_PRESETS",
    "TEMPLATE_REGISTRY",
    "get_template",
    "list_templates",
    "renderer_root",
    "template_dir",
]
