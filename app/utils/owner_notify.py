"""L1 owner egress — the missing Telegram delivery layer (M4, crore-strategy T03).

WHY THIS EXISTS
---------------
ARCH §8 R5: `owner_notify` grep → **0 hits**. The feed store
(`app/utils/owner_feed.py`) exists and is TEST-PROVEN, but there was **no egress**:
the owner received nothing. This module is the L1 delivery layer of
`docs/context/OWNER_TELEGRAM_FEED_DESIGN.md`.

DESIGN RULES (non-negotiable — ARCH §M4 / §7)
----------------------------------------------
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
7. **Multi-token fallback.** Mirrors `telegram_egress._token_candidates()`: Notify
   bot first, JARVIS bot fallback — so one revoked token cannot silence all alerts.
8. **Truthful sync result from async callers.** If a running event loop exists
   (async caller), delivery executes in a one-shot worker thread instead of
   deadlocking the loop — the returned bool still reflects the ACTUAL delivery
   outcome, never an optimistic guess.

Truth gate: events sourced from `workforce` are force-`UNVERIFIED` (see owner_feed).
Evidence label: CODE-PRESENT (new module, pinned by tests/test_owner_notify.py).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Per-hour dedupe window + rate cap (per chat group). The owner must never be spammed.
_DEDUPE_WINDOW_S = 3600.0
_RATE_MAX_PER_HOUR = 30
_DELIVER_TIMEOUT_S = 30.0

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

# Chat ID target for owner direct DM — used when group-based routing fails.
# Read from env so it can be overridden per-deployment without code change.
_OWNER_DM_CHAT_ID = "TELEGRAM_CHAT_ID"


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


def _fp(v: str) -> str:
    """SHA-256 fingerprint prefix of a secret value. Never prints the secret."""
    return hashlib.sha256((v or "").encode("utf-8")).hexdigest()[:12]


def _run_delivery(coro_fn) -> dict:
    """Run a delivery coroutine to completion; result stays truthful.

    - No running loop (sync caller) → `asyncio.run` directly.
    - Running loop (async caller) → one-shot worker thread runs a fresh
      `asyncio.run` so the sync bool reflects the ACTUAL outcome without
      deadlocking the caller's loop. Bounded by `_DELIVER_TIMEOUT_S`.
    Never raises; timeout/error → `{"sent": False, ...}` (fail-open).

    IMPORTANT: `coro_fn` is called INSIDE the execution context (worker
    thread for async callers), NOT in the caller thread, so the coroutine
    object is created where it will actually run.
    """
    try:
        try:
            asyncio.get_running_loop()
            in_running_loop = True
        except RuntimeError:
            in_running_loop = False
        if not in_running_loop:
            # Sync caller — safe to run the loop here.
            return asyncio.run(coro_fn())
        # Async caller — run in a one-shot worker thread so we can BLOCK
        # for a truthful result without deadlocking the caller's loop.
        # The coroutine factory is called INSIDE the worker thread so the
        # coroutine is created in a clean context (no shared loop state).
        def _run_in_worker():
            return asyncio.run(coro_fn())
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_in_worker)
            return future.result(timeout=_DELIVER_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        logger.warning("[owner_notify] delivery timed out (fail-open)")
        return {"sent": False, "error": "delivery_timeout"}
    except Exception as e:  # fail-open by design
        logger.warning("[owner_notify] delivery error (fail-open): %s", e)
        return {"sent": False, "error": str(e)[:200]}


def _get_token_candidates() -> list[str]:
    """Get all configured Telegram bot tokens in priority order.
    Mirrors telegram_egress._token_candidates() exactly.
    """
    try:
        from app.utils import telegram_egress
        return telegram_egress._token_candidates()
    except Exception:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        return [token] if token else []


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

    Uses multi-token fallback (Notify → JARVIS) via telegram_egress._token_candidates().
    Falls back to direct DM via TELEGRAM_CHAT_ID env when group chat is unavailable.

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
            _mirror_feed(sev, source, actor, body, evidence or "", verified, dedupe_key)
            return False

        target_group = _resolve_group(sev, group)

        # Rate-limit — never spam.
        if not _rate_ok(target_group):
            logger.warning("[owner_notify] rate-limited group=%s (dropping)", target_group)
            _mirror_feed(sev, source, actor, body, evidence or "", verified, dedupe_key)
            return False

        emoji = {"P0": "🔴", "P1": "🟡", "info": "ℹ️"}.get(sev, "ℹ️")
        message = f"{emoji} {sev} {body}"

        # Mirror to the canonical feed store (evidence, traceability).
        _mirror_feed(sev, source, actor, message, evidence or "", verified, dedupe_key)

        if dry_run:
            return True

        # Fail-open delivery with multi-token fallback + DM fallback.
        sent = _deliver_fallback(target_group, message)
        return sent
    except Exception as e:  # pragma: no cover — fail-open by design
        logger.warning("[owner_notify] send_owner failed (fail-open): %s", e)
        return False


def _deliver_fallback(group: str, message: str) -> bool:
    """Try group-based delivery, then fall back to DM if group chat is invalid.

    1. Try telegram_egress.send_to_group(group, message) — uses multi-token fallback.
    2. If that fails with 'chat not found', try sending to TELEGRAM_CHAT_ID env directly.
    Never raises. Returns True on any successful send.
    """
    # Path 1: group-based delivery (multi-token fallback built into telegram_egress)
    try:
        from app.utils.telegram_egress import send_to_group
        result = _run_delivery(lambda: send_to_group(group, message))
        if result.get("sent"):
            # Log only proven facts: destination + receipt message_id. Which
            # token actually delivered is NOT asserted here (no evidence in
            # the receipt) — no "via JARVIS" style claims.
            logger.info(
                "[owner_notify] delivered to group=%s message_id=%s",
                group,
                result.get("message_id"),
            )
            return True
        logger.warning(
            "[owner_notify] group delivery failed group=%s: %s",
            group,
            result.get("error", "unknown"),
        )
    except Exception as e:
        logger.warning("[owner_notify] group delivery exception: %s", e)

    # Path 2: direct DM fallback to TELEGRAM_CHAT_ID.
    # Telegram Bot API sendMessage REQUIRES chat_id in the request body —
    # pass the recipient explicitly alongside the message text.
    dm_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not dm_chat:
        logger.warning("[owner_notify] no TELEGRAM_CHAT_ID for DM fallback")
        return False
    try:
        from app.utils.telegram_egress import _send_via_bot_api
        dm_payload = {"chat_id": dm_chat, "text": message}
        result = _run_delivery(lambda: _send_via_bot_api(dm_chat, "sendMessage", dm_payload))
        if result.get("sent"):
            logger.info(
                "[owner_notify] delivered to DM chat=%s message_id=%s",
                dm_chat,
                result.get("message_id"),
            )
            return True
        logger.warning("[owner_notify] DM delivery failed: %s", result.get("error", "unknown"))
    except Exception as e:
        logger.warning("[owner_notify] DM delivery exception: %s", e)

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
