"""Headless Telegram ingress for the 24x7 control plane (SCAFFOLD, fail-closed).

CONTEXT
-------
Today the Hermes Desktop app is the **sole** Telegram ``getUpdates`` consumer
(``docs/context/WORKER_ROSTER.md``). The owner-command-center architecture wants
a headless ingress so owner notifications / approvals keep flowing even when the
desktop GUI is closed. This module is that ingress.

SAFETY (read before enabling)
-----------------------------
* Gated by ``TELEGRAM_INGRESS_ENABLED`` — DEFAULT OFF (0). When off, every entry
  point returns ``{"ok": False, "reason": "disabled"}`` and performs NO network
  call. This is the fail-closed default; Hermes can keep polling unchanged.
* Even when enabled, it requires the owner-gated bot token (T-01). No token =>
  ``{"ok": False, "reason": "token_unconfigured"}``. Never raises on missing creds.
* This is a SCAFFOLD: it does NOT yet own the ``getUpdates`` long-poll. The actual
  poll loop is intentionally left as a clearly-marked TODO pending (a) T-01 Telegram
  credential provisioning and (b) the owner's decision on re-homing Hermes's
  existing consumer (avoid double-consumption). Enabling the flag without those two
  things resolved simply yields a no-op with an honest reason — it will never
  silently claim to have ingested messages.

It is importable + unit-testable: tests assert the fail-closed posture, which is
the behaviour that matters for 24x7 safety.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_FLAG = "TELEGRAM_INGRESS_ENABLED"
_TOKEN_ENV = "TELEGRAM_INGRESS_BOT_TOKEN"  # nosecret: env var NAME, never a value
_TOKEN_MIN_CHARS = 20


def telegram_ingress_enabled() -> bool:
    return os.getenv(_FLAG, "0").strip().lower() in {"1", "true", "yes", "on"}


def _token_configured() -> bool:
    secret = os.getenv(_TOKEN_ENV, "").strip()
    return len(secret) >= _TOKEN_MIN_CHARS


def readiness() -> dict[str, Any]:
    """Honest posture probe — no side effects, no network."""
    if not telegram_ingress_enabled():
        return {"ok": False, "enabled": False, "reason": "disabled"}
    if not _token_configured():
        return {"ok": False, "enabled": True, "reason": "token_unconfigured"}
    return {"ok": True, "enabled": True, "reason": "ready"}


async def run_ingress_once(db=None) -> dict[str, Any]:
    """One ingress pass. Fail-closed scaffold.

    Returns an honest status. Performs NO network I/O until both the flag is on
    AND the owner-gated token is configured. The real poll loop is a TODO pending
    T-01 creds + the Hermes double-consumption decision (see module docstring).
    """
    status = readiness()
    if not status["ok"]:
        logger.info("[telegram_ingress] skip: %s", status["reason"])
        return status

    # TODO(owner-gated T-01): implement the getUpdates long-poll here and enqueue
    # inbound owner messages / approvals as DevTask rows (with audit events). Must
    # coordinate with Hermes's existing consumer to avoid double-consumption.
    logger.warning(
        "[telegram_ingress] enabled + token present but poll loop NOT implemented "
        "(scaffold). No messages ingested. Resolve T-01 + Hermes handoff before "
        "treating this as live."
    )
    return {"ok": True, "enabled": True, "reason": "scaffold_not_implemented", "ingested": 0}


__all__ = ["telegram_ingress_enabled", "readiness", "run_ingress_once"]
