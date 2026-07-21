"""Outbound OpenClaw client — DEPRECATED / optional callback only.

Preferred architecture (ADR-OPENCLAW-OWNER-COPILOT):
  OpenClaw Gateway initiates requests → LeadGen /api/owner-copilot/*
  LeadGen core runtime does NOT depend on OpenClaw.

OPENCLAW_BASE_URL is retained only for an optional best-effort callback
(notify_gateway). It must never be required for Owner Copilot commands.
Default empty = no-op. Failures never affect SaaS availability.
"""

from __future__ import annotations

import os
from typing import Any

from app.integrations.openclaw.policies import openclaw_enabled, request_timeout_seconds
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def base_url() -> str:
    return (os.getenv("OPENCLAW_BASE_URL") or "").strip().rstrip("/")


def outbound_configured() -> bool:
    """True only when an optional callback URL is set AND feature enabled."""
    return bool(base_url()) and openclaw_enabled()


async def notify_gateway(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Optional callback. Never raises; never blocks core flows; no retries that fan out."""
    if not outbound_configured():
        return {
            "ok": False,
            "skipped": True,
            "reason": "inbound_only_or_callback_unset",
            "note": "OPENCLAW_BASE_URL unused for command path — OpenClaw calls LeadGen",
        }
    url = f"{base_url()}/hooks/leadgen-owner-copilot"
    token = (os.getenv("OPENCLAW_API_TOKEN") or "").strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        import httpx

        timeout = request_timeout_seconds()
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json={"event": event, "payload": payload}, headers=headers)
            return {"ok": r.status_code < 400, "status_code": r.status_code}
    except Exception as exc:
        logger.warning("openclaw optional callback failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}
