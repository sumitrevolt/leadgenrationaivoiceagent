"""Staged video-creative pipeline for Product One — replaces reel_video's flat
PIL-slide template with brand overlay + Ken-Burns motion + captions + optional
music, on an isolated `video` Celery queue. Phase 1 = generic recipe only.

Never raises across the public entry point — same convention as reel_video,
content_approval, delivery_ledger. See docs/superpowers/specs/
2026-07-10-product-one-video-creative-pipeline-design.md for full design.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _logo_temp_file(logo_data_uri: str, tmp_dir: str) -> str | None:
    """brand_frames.resolve_brand()'s logo_data_uri (data:image/...;base64,...)
    ko ek disk file me decode karo — ffmpeg ko file path chahiye, data URI nahi.
    Never raises; malformed/empty input = None."""
    try:
        if not logo_data_uri or not logo_data_uri.startswith("data:image/"):
            return None
        header, _, b64_payload = logo_data_uri.partition(",")
        if not b64_payload:
            return None
        ext = "png"
        if "jpeg" in header or "jpg" in header:
            ext = "jpg"
        elif "webp" in header:
            ext = "webp"
        raw = base64.b64decode(b64_payload, validate=False)
        if not raw:
            return None
        path = os.path.join(tmp_dir, f"logo.{ext}")
        with open(path, "wb") as f:
            f.write(raw)
        return path
    except Exception as e:
        logger.warning(f"[video_pipeline] logo decode failed: {e}")
        return None


async def render_creative_video(
    recipe: str = "generic",
    *,
    business_name: str,
    niche: str = "general",
    slides: list[str] | None = None,
    offer: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    """1 branded creative video banao. Returns {path,...} ya {error}.
    Phase 1: recipe is accepted but only "generic" has a real implementation;
    delegates to reel_video.build_reel unchanged (walking skeleton)."""
    from app.marketing import reel_video

    return await reel_video.build_reel(
        business_name=business_name,
        niche=niche,
        slides=slides,
        offer=offer,
        client_id=client_id,
    )
