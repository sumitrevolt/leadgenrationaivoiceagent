"""Deprecated — Razorpay payment links removed 2026-06-18.

Razorpay gateway ko poora hata diya gaya (manual UPI hi payment path). Yeh module
ab inert stub hai — koi gateway call nahi karta. Client-facing payment-link UI
removed; payments manual UPI/contact se. Functions safe no-ops return karte hain
taaki koi stale import crash na kare. Never raises.
"""

from __future__ import annotations

from typing import Any


def is_configured() -> bool:
    """Razorpay removed — payment links permanently disabled."""
    return False


def build_wa_share_link(*_args: Any, **_kwargs: Any) -> str:
    """No-op (Razorpay removed)."""
    return ""


def list_payment_links(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
    """No-op (Razorpay removed) — always empty."""
    return []


async def create_payment_link(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """No-op (Razorpay removed) — payment links feature disabled."""
    return {
        "ok": False,
        "error": "Payment links band kar diye gaye — abhi manual UPI/contact se payment lein.",
    }


__all__ = ["create_payment_link", "list_payment_links", "build_wa_share_link", "is_configured"]
