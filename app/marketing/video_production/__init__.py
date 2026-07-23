"""OpenClaw-governed Daily Video Production Cell.

Authoritative reuse: video_ad_cycle + video_pipeline + content_approval + postiz.
This package adds state machine, feedback classification, WhatsApp review,
publish gating, and harness tool registrations — not a second agent framework.
"""

from __future__ import annotations

from app.marketing.video_production.cell import (
    approve_version,
    create_daily_brief,
    ops_summary,
    render_and_queue_review,
    schedule_approved,
    write_script,
)
from app.marketing.video_production.feedback import classify_feedback
from app.marketing.video_production.flags import flag_snapshot
from app.marketing.video_production.publish_gate import assert_can_publish
from app.marketing.video_production.shadow import counters as shadow_counters
from app.marketing.video_production.shadow import run_shadow_matrix

# Register harness tools on import (idempotent).
try:
    from app.marketing.video_production.harness_tools import register_video_tools

    register_video_tools()
except Exception:
    pass

__all__ = [
    "approve_version",
    "assert_can_publish",
    "classify_feedback",
    "create_daily_brief",
    "flag_snapshot",
    "ops_summary",
    "render_and_queue_review",
    "run_shadow_matrix",
    "schedule_approved",
    "shadow_counters",
    "write_script",
]
