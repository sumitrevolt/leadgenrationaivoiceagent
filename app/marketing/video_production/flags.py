"""Video Production Cell feature flags — all default OFF (fail-closed).

Legacy alias: VIDEO_AD_CYCLE remains authoritative for the scheduler cycle.
New VIDEO_* flags add finer gates (WhatsApp review, social publish, harness).
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
    return _on("VIDEO_CUSTOMER_REVIEW_ENABLED") or production_enabled()


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


def own_brand_enabled() -> bool:
    return _on("VIDEO_OWN_BRAND_ENABLED")


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
        "VIDEO_OWN_BRAND_ENABLED": own_brand_enabled(),
        "VIDEO_AD_CYCLE": _on("VIDEO_AD_CYCLE"),
    }


__all__ = [
    "production_enabled",
    "daily_scheduler_enabled",
    "customer_review_enabled",
    "whatsapp_review_enabled",
    "social_publish_enabled",
    "harness_enforce",
    "own_brand_enabled",
    "flag_snapshot",
]
