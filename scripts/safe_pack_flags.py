"""Owner-locked Revenue Automation Max SAFE pack keys (2026-08-05).

Exact env names only — no aliases. Used by canary script + Mission Control
highlight contract tests. Does NOT write .env (see safe_pack_flag_canary.sh).
"""

from __future__ import annotations

# Capability → keys (repo truth: AUTOMATION_FLAGS + team_scheduler gates)
SAFE_PACK_KEYS: tuple[str, ...] = (
    "FLOW_RUNNER",
    "FLOW_AUTO_TRIGGERS",
    "PROCESS_ENGINE",
    "PROCESS_AUTOSTART",
    "REVENUE_TRENDS",
    "CONTENT_APPROVAL_AUTO",  # approval QUEUE submit only — not publish/approve
)

# Explicitly not approved for this pack (must never be set by safe-pack tools)
NEVER_TOUCH: frozenset[str] = frozenset(
    {
        "SALES_AUTOPILOT_WHATSAPP_ENABLED",
        "REPLY_AUTO_SEND",
        "REPLY_AUTO_SEND_HARD_OFF",
        "UPI_AUTO_ACTIVATE",
        "ALLOW_TOS_SCRAPE",
        "CREATIVE_OS_ENABLED",
        "VOICE_LAUNCH_KILL",
        "PLATFORM_DIAL_DAILY",
        "WHATSAPP_AUTO_SEND",
    }
)


def assert_safe_pack_disjoint() -> None:
    overlap = set(SAFE_PACK_KEYS) & NEVER_TOUCH
    if overlap:
        raise SystemExit(f"SAFE_PACK overlaps NEVER_TOUCH: {sorted(overlap)}")
