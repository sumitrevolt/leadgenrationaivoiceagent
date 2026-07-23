"""Video Production Cell feature flags — all default OFF (fail-closed).

Legacy alias: VIDEO_AD_CYCLE remains authoritative for the scheduler cycle.
New VIDEO_* flags add finer gates (WhatsApp review, social publish, harness).

Stage 1 shadow posture (local/hermetic only — never flip WA/social/own-brand):
  VIDEO_PRODUCTION_ENABLED=1
  VIDEO_HARNESS_SHADOW_ENABLED=1
  VIDEO_HARNESS_ENFORCE=0
  VIDEO_DAILY_SCHEDULER_ENABLED=0
  VIDEO_CUSTOMER_REVIEW_ENABLED=0
  VIDEO_WHATSAPP_REVIEW_ENABLED=0
  VIDEO_SOCIAL_PUBLISH_ENABLED=0
  VIDEO_OWN_BRAND_ENABLED=0
"""

from __future__ import annotations

import os


def _on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def production_enabled() -> bool:
    """Master kill for the governed Video Production Cell APIs/orchestration."""
    return _on("VIDEO_PRODUCTION_ENABLED")


def daily_scheduler_enabled() -> bool:
    """Daily planning job. Also honors legacy VIDEO_AD_CYCLE."""
    return _on("VIDEO_DAILY_SCHEDULER_ENABLED") or _on("VIDEO_AD_CYCLE")


def customer_review_enabled() -> bool:
    """Customer dashboard review surfaces — explicit only.

    Stage 1 requires VIDEO_PRODUCTION_ENABLED=1 with review still OFF, so this
    must NOT auto-enable from the production master switch.
    """
    return _on("VIDEO_CUSTOMER_REVIEW_ENABLED")


def whatsapp_review_enabled() -> bool:
    """Auto WhatsApp preview send — OFF default; ban-safety critical."""
    return _on("VIDEO_WHATSAPP_REVIEW_ENABLED")


def social_publish_enabled() -> bool:
    """Approval-gated Postiz/social publish. OFF = publish_due refuse."""
    if _on("VIDEO_SOCIAL_PUBLISH_ENABLED"):
        return True
    # Legacy: VIDEO_AD_CYCLE alone used to publish — keep that path when
    # production cell master is OFF so existing behaviour is unchanged.
    if not production_enabled():
        return True
    return False


def harness_enforce() -> bool:
    """When ON, harness evaluate_action must allow before mutating tools run."""
    return _on("VIDEO_HARNESS_ENFORCE")


def harness_shadow() -> bool:
    """Stage 1: observe harness decisions without enforcement or side effects."""
    return _on("VIDEO_HARNESS_SHADOW_ENABLED")


def own_brand_enabled() -> bool:
    return _on("VIDEO_OWN_BRAND_ENABLED")


def stage1_shadow_active() -> bool:
    """True when Stage 1 shadow posture is correctly set (side-effect flags OFF)."""
    return (
        production_enabled()
        and harness_shadow()
        and not harness_enforce()
        and not daily_scheduler_enabled()
        and not customer_review_enabled()
        and not whatsapp_review_enabled()
        and not _on("VIDEO_SOCIAL_PUBLISH_ENABLED")
        and not own_brand_enabled()
    )


def flag_snapshot() -> dict[str, bool]:
    return {
        "VIDEO_PRODUCTION_ENABLED": production_enabled(),
        "VIDEO_DAILY_SCHEDULER_ENABLED": daily_scheduler_enabled(),
        "VIDEO_CUSTOMER_REVIEW_ENABLED": customer_review_enabled(),
        "VIDEO_WHATSAPP_REVIEW_ENABLED": whatsapp_review_enabled(),
        "VIDEO_SOCIAL_PUBLISH_ENABLED": (
            social_publish_enabled()
            if production_enabled()
            else _on("VIDEO_SOCIAL_PUBLISH_ENABLED")
        ),
        "VIDEO_HARNESS_ENFORCE": harness_enforce(),
        "VIDEO_HARNESS_SHADOW_ENABLED": harness_shadow(),
        "VIDEO_OWN_BRAND_ENABLED": own_brand_enabled(),
        "VIDEO_AD_CYCLE": _on("VIDEO_AD_CYCLE"),
        "stage1_shadow_active": stage1_shadow_active(),
    }


__all__ = [
    "production_enabled",
    "daily_scheduler_enabled",
    "customer_review_enabled",
    "whatsapp_review_enabled",
    "social_publish_enabled",
    "harness_enforce",
    "harness_shadow",
    "own_brand_enabled",
    "stage1_shadow_active",
    "flag_snapshot",
]
