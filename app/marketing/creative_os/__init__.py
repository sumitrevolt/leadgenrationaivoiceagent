"""Creative Automation OS — governed extension of Video Production Cell (ADR-143).

Additive layer over video_pipeline / video_ad_cycle / video_production / Postiz.
All CREATIVE_* flags default OFF. Never raises across public service entry points.
"""

from __future__ import annotations

from app.marketing.creative_os.flags import flag_snapshot, os_enabled
from app.marketing.creative_os.service import (
    approve_exact,
    enqueue_generate,
    generate_preview,
    list_cockpit,
    process_generation,
    quarantine,
    request_changes,
)

__all__ = [
    "approve_exact",
    "enqueue_generate",
    "flag_snapshot",
    "generate_preview",
    "list_cockpit",
    "os_enabled",
    "process_generation",
    "quarantine",
    "request_changes",
]
