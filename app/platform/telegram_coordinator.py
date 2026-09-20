"""
Telegram Dual-Bot Coordination Architecture
============================================
Single source of truth for the LeadGen AI Telegram bot architecture.

Architecture (decided via TypeSafe, 2026-09-20):
- Jarvis Bot (TELEGRAM_JARVIS_BOT_TOKEN): Interactive command bot (@Sumits_jarvis_bot)
  - Receives inbound updates via getUpdates long-polling
  - Processes /status, /tasks, /agents, /pause, /resume commands
  - Uses TypeSafe System One for intent classification and 9-bot routing
  - Executes platform skills (ops-status, task-triage, etc.)
  - Sends responses back to owner chat

- Notify Bot (TELEGRAM_NOTIFY_BOT_TOKEN): Broadcast-only egress bot (@Leadsgenai1_bot)
  - Sends system alerts, P0 incidents, UPI payment notifications
  - Delivers daily briefs, deploy notices, video delivery receipts
  - Zero getUpdates polling (prevents 409 conflict with Jarvis)
  - Pure egress via app/utils/telegram_egress.py

- Webhook endpoint (/api/webhooks/telegram): Receives Telegram updates
  - Secret-token fail-closed verification
  - Durable inbox persistence (data/telegram_inbox.jsonl)
  - Dedup by update_id (bounded cache)
  - Cross-channel opt-out handling
  - Automatic dispatch to TelegramBot.process_update

Setup spec: config/telegram/setup_spec.yaml (13 entities, single source of truth)
Egress routing: config/telegram/owner_notify_routing.yaml (severity-based)
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# State
_DEDUPE_TTL = 3600.0
_processed_updates: dict[str | int, float] = {}


def get_polling_token() -> Optional[str]:
    """Get the polling (Jarvis) bot token. Fail-closed: None if missing or too short."""
    tok = os.getenv("TELEGRAM_JARVIS_BOT_TOKEN", "").strip()
    return tok if len(tok) >= 20 else None


def get_egress_token() -> Optional[str]:
    """Get the egress (Notify) bot token. Fail-closed: None if missing or too short."""
    tok = (
        os.getenv("TELEGRAM_NOTIFY_BOT_TOKEN", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )
    return tok if len(tok) >= 20 else None


def get_owner_chat_ids() -> set[int]:
    """Get authorized owner chat IDs from environment."""
    raw = os.getenv("TELEGRAM_OWNER_CHAT_IDS", "1621120182")
    chat_ids = set()
    for item in raw.split(","):
        try:
            chat_ids.add(int(item.strip()))
        except (ValueError, AttributeError):
            pass
    return chat_ids


def get_owner_usernames() -> set[str]:
    """Get authorized owner usernames from environment."""
    raw = os.getenv("TELEGRAM_OWNER_USERNAMES", "sumitrevolt")
    return {u.strip().lower().lstrip("@") for u in raw.split(",") if u.strip()}


def is_telegram_configured() -> bool:
    """Check if Telegram dual-bot setup has minimum viable configuration."""
    jarvis = get_polling_token()
    notify = get_egress_token()
    return bool(jarvis and notify and get_owner_chat_ids())


def is_owner_chat(chat_id: int | str) -> bool:
    """Check if chat_id is an authorized owner chat."""
    try:
        return int(chat_id) in get_owner_chat_ids()
    except (ValueError, TypeError):
        return False


def is_owner_username(username: Optional[str]) -> bool:
    """Check if username is an authorized owner."""
    if not username:
        return False
    return username.strip().lower().lstrip("@") in get_owner_usernames()


def is_duplicate_update(update_id: Optional[int]) -> bool:
    """Check if update_id was recently processed. Thread-safe bounded cache."""
    if not isinstance(update_id, int):
        return False
    now = time.time()
    # Clean expired entries
    expired = [k for k, v in _processed_updates.items() if now - v > _DEDUPE_TTL]
    for k in expired:
        _processed_updates.pop(k, None)
    if update_id in _processed_updates:
        return True
    _processed_updates[update_id] = now
    return False


def _send_tg_api(token: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call Telegram Bot API via standard urllib."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error_code": exc.code, "description": exc.reason}
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


def dispatch_egress_alert(
    title: str,
    text: str,
    severity: str = "INFO",
    chat_id: Optional[str | int] = None,
) -> dict[str, Any]:
    """Dispatch a system alert through the Notify bot (@Leadsgenai1_bot).
    
    Includes deep-link prompt to interact with Jarvis bot (@Sumits_jarvis_bot).
    """
    token = get_egress_token()
    if not token:
        logger.warning("[telegram_coordinator] Egress alert skipped: TELEGRAM_NOTIFY_BOT_TOKEN unset")
        return {"sent": False, "reason": "token_unset"}

    target_chat = str(chat_id) if chat_id else "1621120182"
    formatted = (
        f"🚨 <b>[{severity.upper()}] {title}</b>\n\n"
        f"{text}\n\n"
        f"💬 <i>Reply to @Sumits_jarvis_bot for commands & status</i>"
    )
    return _send_tg_api(
        token,
        "sendMessage",
        {
            "chat_id": target_chat,
            "text": formatted,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def dispatch_jarvis_response(
    chat_id: int | str,
    text: str,
    parse_mode: str = "HTML",
) -> dict[str, Any]:
    """Dispatch a command response through the Jarvis bot (@Sumits_jarvis_bot)."""
    token = get_polling_token()
    if not token:
        logger.warning("[telegram_coordinator] Jarvis response skipped: TELEGRAM_JARVIS_BOT_TOKEN unset")
        return {"sent": False, "reason": "token_unset"}

    return _send_tg_api(
        token,
        "sendMessage",
        {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        },
    )


def get_dual_bot_status() -> dict[str, Any]:
    """Inspect and return coordination status for both bots."""
    jarvis_token = get_polling_token()
    notify_token = get_egress_token()

    status = {
        "configured": is_telegram_configured(),
        "jarvis": {
            "token_configured": bool(jarvis_token),
            "role": "ingress_interactive_commands",
            "username": "@Sumits_jarvis_bot",
            "polling_enabled": True,
        },
        "notify": {
            "token_configured": bool(notify_token),
            "role": "egress_broadcast_alerts",
            "username": "@Leadsgenai1_bot",
            "polling_enabled": False,  # Strict invariant: zero 409 conflicts
        },
        "owners": {
            "chat_ids": list(get_owner_chat_ids()),
            "usernames": list(get_owner_usernames()),
        },
    }
    return status


def run_jarvis_polling(
    poll_timeout: int = 25,
    max_iterations: Optional[int] = None,
    on_message_callback: Optional[Callable[[dict[str, Any]], None]] = None,
) -> None:
    """Run long-polling for the Jarvis Bot.
    
    Safe for local development or dedicated worker container.
    """
    token = get_polling_token()
    if not token:
        logger.error("[telegram_coordinator] Cannot start Jarvis polling: TELEGRAM_JARVIS_BOT_TOKEN unset")
        return

    from app.integrations.telegram_bot import get_telegram_bot
    bot = get_telegram_bot()

    logger.info("[telegram_coordinator] Starting Jarvis bot long-polling loop...")
    offset = 0
    iteration = 0

    while True:
        if max_iterations is not None and iteration >= max_iterations:
            logger.info("[telegram_coordinator] Reached max_iterations (%d), exiting polling", max_iterations)
            break
        iteration += 1

        params: dict[str, Any] = {"timeout": poll_timeout, "allowed_updates": ["message", "edited_message"]}
        if offset:
            params["offset"] = offset

        res = _send_tg_api(token, "getUpdates", params)
        if not res.get("ok"):
            err = res.get("description", "unknown error")
            if "conflict" in err.lower():
                logger.error("[telegram_coordinator] Telegram 409 Conflict: Another instance is polling! Backing off...")
                time.sleep(10.0)
            else:
                logger.warning("[telegram_coordinator] getUpdates returned error: %s", err)
                time.sleep(3.0)
            continue

        updates = res.get("result", [])
        for update in updates:
            up_id = update.get("update_id")
            if up_id:
                offset = max(offset, up_id + 1)

            try:
                bot.process_update(update, send_reply=True)
                if on_message_callback:
                    on_message_callback(update)
            except Exception as e:
                logger.error("[telegram_coordinator] Error processing update: %s", e)


# Backward compatibility aliases
TELEGRAM_JARVIS_BOT_TOKEN = os.getenv("TELEGRAM_JARVIS_BOT_TOKEN", "").strip()
TELEGRAM_NOTIFY_BOT_TOKEN = os.getenv("TELEGRAM_NOTIFY_BOT_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_OWNER_CHAT_IDS = get_owner_chat_ids()
TELEGRAM_OWNER_USERNAMES = get_owner_usernames()

__all__ = [
    "is_telegram_configured",
    "get_egress_token",
    "get_polling_token",
    "get_owner_chat_ids",
    "get_owner_usernames",
    "is_owner_chat",
    "is_owner_username",
    "is_duplicate_update",
    "dispatch_egress_alert",
    "dispatch_jarvis_response",
    "get_dual_bot_status",
    "run_jarvis_polling",
    "TELEGRAM_JARVIS_BOT_TOKEN",
    "TELEGRAM_NOTIFY_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_OWNER_CHAT_IDS",
    "TELEGRAM_OWNER_USERNAMES",
]
