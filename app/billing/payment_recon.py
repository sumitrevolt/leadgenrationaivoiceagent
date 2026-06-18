"""Deprecated — Razorpay payment reconciliation removed 2026-06-18.

Razorpay gateway poora hata diya gaya — reconciliation ka koi source nahi raha
(payments ab manual UPI). Yeh module inert stub hai; functions safe no-ops return
karte hain taaki stale imports/scheduler hooks crash na karein. Never raises.
"""

from __future__ import annotations

from typing import Any


def match_payments(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """No-op (Razorpay removed)."""
    return {"total_payments": 0, "gross_inr": 0, "matched": 0, "unmatched": []}


async def run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """No-op (Razorpay removed) — reconciliation disabled."""
    return {"ok": False, "skipped": "razorpay removed"}


async def run_if_enabled(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """No-op (Razorpay removed)."""
    return {"ok": False, "skipped": "razorpay removed"}


def last_report() -> dict[str, Any]:
    """No-op (Razorpay removed)."""
    return {"ok": False, "note": "razorpay removed — payment recon disabled"}
