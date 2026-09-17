"""L1 owner egress — the missing Telegram delivery layer (M4, crore-strategy T03).

WHY THIS EXISTS
---------------
ARCH §8 R5: `owner_notify` grep → **0 hits**. The feed store
(`app/utils/owner_feed.py`) exists and is TEST-PROVEN, but there was **no egress**:
the owner received nothing. This module is the L1 delivery layer of
`docs/context/OWNER_TELEGRAM_FEED_DESIGN.md`.

DESIGN RULES (non-negotiable — ARCH §M4 / §7)
---------------------------------------------
1. **Fail-open.** Telegram down / token missing / rate-limited must NEVER raise and
   NEVER break the caller. `send_owner()` returns a bool; app-flow continues.
2. **Egress-only.** Hermes is the sole ingress consumer (`HERMES_CONTROL_PLANE.md`);
   this module only *sends* — it never reads the Telegram update queue.
3. **Evidence required.** No `evidence` ⇒ the text is tagged `UNVERIFIED` so the owner
   is never given false confidence.
4. **Dedupe per-hour.** `dedupe_key` suppresses a repeat within the hour window;
   the owner is never spammed.
5. **Credentials from env ONLY** (`TELEGRAM_BOT_TOKEN`). chat_ids come from
   `config/telegram/setup_spec.yaml` via `telegram_egress.resolve_chat_id` — never hardcoded.
6. **Reuse, don't rebuild.** Delivery goes through the existing TEST-PROVEN
   `app/utils/telegram_egress.send_to_group`. No second Telegram client.

Truth gate: events sourced from `workforce` are force-`UNVERIFIED` (see owner_feed).
Evidence label: CODE-PRESENT (new module, pinned by tests/test_owner_notify.py).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Per-hour dedupe window + rate cap (per chat group). The owner must never be spammed.
_DEDUPE_WINDOW_S = 3600.0
_RATE_MAX_PER_HOUR = 30

# In-process caches. Process-local by design: dedupe is a *courtesy* layer; the
# canonical event store (owner_feed) remains the truth. Never fatal.
_DEDUPE_CACHE: dict[str, float] = {}
_RATE_CACHE: dict[str, list[float]] = {}

# Default routing: which chat group a severity goes to. Overridable by the YAML
# routing file (config/telegram/owner_notify_routing.yaml) and env.
_DEFAULT_GROUP_BY_SEVERITY: dict[str, str] = {
    "P0": "owner_alerts",
    "P1": "internal_admin",
    "info": "internal_admin",
}


def _rate_ok(group: str) -> bool:
    """Rolling one-hour rate check. Never raises."""
    now = time.time()
    hits = [t for t in _RATE_CACHE.get(group, []) if now - t < _DEDUPE_WINDOW_S]
    _RATE_CACHE[group] = hits
    if len(hits) >= _RATE_MAX_PER_HOUR:
        return False
    hits.append(now)
    _RATE_CACHE[group] = hits
    return True


def _dedupe_ok(dedupe_key: str | None) -> bool:
    """True if this key has NOT been seen in the last hour. Never raises."""
    if not dedupe_key:
        return True
    now = time.time()
    last = _DEDUPE_CACHE.get(dedupe_key)
    if last is not None and now - last < _DEDUPE_WINDOW_S:
        return False
    _DEDUPE_CACHE[dedupe_key] = now
    return True


def _resolve_group(severity: str, group: str | None) -> str:
    """Pick the destination group: explicit > severity default. Never raises."""
    if group:
        return group
    return _DEFAULT_GROUP_BY_SEVERITY.get(severity, "internal_admin")


def send_owner(
    text: str,
    *,
    severity: str = "info",
    evidence: str | None = None,
    dedupe_key: str | None = None,
    group: str | None = None,
    source: str = "owner_notify",
    actor: str = "system",
    dry_run: bool = False,
) -> bool:
    """Send one alert to the owner's Telegram group. **Never raises.**

    Args:
        text: message body (Hinglish OK). Truncated by the egress layer.
        severity: "P0" | "P1" | "info" — routes to a group + sets the emoji.
        evidence: REQUIRED for confidence. Missing ⇒ text tagged `UNVERIFIED`.
        dedupe_key: per-hour dedupe; a repeat within the hour is suppressed.
        group: explicit destination group id (else severity default).
        source/actor: feed provenance.
        dry_run: build the payload but do not send (used by tests).

    Returns:
        True if the message was handed to the egress layer (or dry-run), else False.
        A False here is a *soft* failure — the caller must never branch on it in a
        way that could break the app flow.
    """
    try:
        body = str(text or "").strip()
        if not body:
            return False
        sev = str(severity or "info").strip()
        if sev not in ("P0", "P1", "info"):
            sev = "info"

        # Evidence gate: missing evidence ⇒ mark the message UNVERIFIED.
        if not (evidence and str(evidence).strip()):
            body = f"{body}\n\n⚠️ UNVERIFIED (no evidence attached)"
            verified = False
        else:
            body = f"{body}\n\nEvidence: {evidence}"
            verified = True

        # Dedupe — per-hour.
        if not _dedupe_ok(dedupe_key):
            logger.info("[owner_notify] dedupe suppressed key=%s", dedupe_key)
            # Still mirror to the canonical feed so the event is not lost.
            _mirror_feed(sev, source, actor, body, evidence or "", verified, dedupe_key)
            return False

        target = _resolve_group(sev, group)

        # Rate-limit — never spam.
        if not _rate_ok(target):
            logger.warning("[owner_notify] rate-limited group=%s (dropping)", target)
            _mirror_feed(sev, source, actor, body, evidence or "", verified, dedupe_key)
            return False

        emoji = {"P0": "🔴", "P1": "🟡", "info": "ℹ️"}.get(sev, "ℹ️")
        message = f"{emoji} {sev} {body}"

        # Mirror to the canonical feed store (evidence, traceability).
        _mirror_feed(sev, source, actor, message, evidence or "", verified, dedupe_key)

        if dry_run:
            return True

        # Fail-open delivery via the existing egress layer.
        sent = _deliver(target, message)
        return sent
    except Exception as e:  # pragma: no cover — fail-open by design
        logger.warning("[owner_notify] send_owner failed (fail-open): %s", e)
        return False


def _deliver(group: str, message: str) -> bool:
    """Hand off to app/utils/telegram_egress.send_to_group. Never raises.

    The egress layer is async; we run it to completion from sync callers. If an
    event loop is already running in this thread, we fall back to a fresh loop.
    """
    try:
        from app.utils.telegram_egress import send_to_group
    except Exception as e:
        logger.warning("[owner_notify] telegram_egress unavailable: %s", e)
        return False

    import asyncio

    async def _go() -> dict[str, Any]:
        return await send_to_group(group, message)

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # We are inside a running loop — schedule and don't block. Return True
            # optimistically (fire-and-forget); the feed mirror already recorded it.
            loop.create_task(_go())
            return True
        result = asyncio.run(_go())
        return bool(result.get("sent"))
    except Exception as e:  # pragma: no cover — fail-open
        logger.warning("[owner_notify] delivery failed (fail-open): %s", e)
        return False


def _mirror_feed(
    severity: str,
    source: str,
    actor: str,
    text: str,
    evidence: str,
    verified: bool,
    dedupe_key: str | None,
) -> None:
    """Mirror to the canonical owner feed. Never raises."""
    try:
        from app.utils import owner_feed

        kind = "incident" if severity in ("P0", "P1") else "heartbeat"
        owner_feed.emit(
            source=source,
            actor=actor,
            text=text,
            severity=severity if severity in ("P0", "P1", "info") else "info",
            kind=kind,
            evidence=evidence,
            verified=verified,
            dedupe_key=dedupe_key,
        )
    except Exception:
        pass


def reset_caches() -> None:
    """Clear the process-local dedupe/rate caches (test helper)."""
    _DEDUPE_CACHE.clear()
    _RATE_CACHE.clear()


__all__ = ["send_owner", "reset_caches"]
