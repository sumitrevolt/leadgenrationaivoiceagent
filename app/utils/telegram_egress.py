"""Telegram egress — send messages/videos to enterprise groups via Bot API.

Mirrors ``config/telegram/setup_spec.yaml`` (canonical group catalog) and
exposes ban-safe, fail-closed, never-raises send helpers for:

  - Owner alerts (ntfy → Telegram mirror)
  - Customer delivery receipts (approved video → customer thread)
  - Ops broadcast (deploy notices, incidents)
  - Community announcements

FAIL-CLOSED (never weakens a compliance gate)
----------------------------------------------
* Missing ``TELEGRAM_BOT_TOKEN`` → every send returns ``{"sent": False}``.
* HTTP errors are logged + counted, never raised.
* Per-message rate limit: 30 messages/second (Telegram Bot API limit).
* Forum topic routing by thread_id (optional).
* All text is truncated to 4096 chars (Bot API max).
* Video caption truncated to 1024 chars (Bot API max for video captions).

Usage::

    from app.utils.telegram_egress import send_to_group, send_video_to_group

    result = await send_to_group("owner_alerts", "💰 Payment received: ₹1,999")
    result = await send_to_group("marketing.announcements", "🚀 New feature live!")
    result = await send_video_to_group("cross.owner_alerts", video_bytes, caption="Deploy OK")
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEXT_MAX = 4096  # Telegram Bot API max message length
_CAPTION_MAX = 1024  # Telegram Bot API max video caption
_RATE_LIMIT_DELAY_S = 0.04  # 25 msg/s (safe margin under 30/s limit)
_TIMEOUT_S = 15.0

_SPEC_PATH = Path(__file__).resolve().parents[2] / "config" / "telegram" / "setup_spec.yaml"

# Map of group_id → chat_id, loaded once from spec
_GROUP_CATALOG: dict[str, str] | None = None


# Tokens confirmed dead (401) at runtime — never retry them this process.
# Populated by _send_via_bot_api on Unauthorized; cleared only on process restart.
_dead_tokens: set[str] = set()


def _vault_notify_token() -> str:
    """Encrypted-vault Notify credential (restart-safe, no plaintext env needed).

    Fail-open to "" when the vault/key-manager is unavailable — the caller still
    falls back to env, and an empty candidate list stays fail-closed.
    Never returns a secret into logs; only same-process in-memory use.
    """
    try:
        from app.platform import key_manager

        value = key_manager.get_key_manager().get_key_value("telegram_notify_bot_token")
        return (value or "").strip()
    except Exception:
        return ""


def _token_candidates() -> list[str]:
    """All configured egress tokens in priority order, dead ones filtered out.

    Priority: env NOTIFY -> encrypted-vault NOTIFY -> env legacy BOT_TOKEN ->
    env JARVIS (last-resort fallback so P0 alerts never silently die).
    """
    vault = _vault_notify_token()
    cands = [
        os.environ.get("TELEGRAM_NOTIFY_BOT_TOKEN", "").strip(),
        vault,
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        os.environ.get("TELEGRAM_JARVIS_BOT_TOKEN", "").strip(),
    ]
    seen: set[str] = set()
    out: list[str] = []
    for t in cands:
        if len(t) >= 20 and t not in _dead_tokens and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _bot_token() -> str | None:
    """Best live egress token. Fail-closed: None if missing.

    Priority: NOTIFY bot (dedicated egress) -> legacy BOT_TOKEN -> JARVIS bot
    (last-resort fallback so P0 alerts NEVER silently die when the Notify
    token is revoked — verified 2026-09-20: TELEGRAM_NOTIFY_BOT_TOKEN was
    401-dead on BOTH local and VPS while JARVIS was valid).
    A token that fails with 401 is blacklisted for this process and the next
    candidate is used, so a revoked Notify token cannot shadow a valid one.
    """
    cands = _token_candidates()
    return cands[0] if cands else None


def _load_group_catalog() -> dict[str, str]:
    """Load chat_id mapping from setup_spec.yaml. Cache in module global."""
    global _GROUP_CATALOG
    if _GROUP_CATALOG is not None:
        return _GROUP_CATALOG
    catalog: dict[str, str] = {}
    try:
        if not _SPEC_PATH.exists():
            logger.warning("[telegram_egress] spec not found: %s", _SPEC_PATH)
            _GROUP_CATALOG = catalog
            return catalog
        with open(_SPEC_PATH, encoding="utf-8") as fh:
            spec = yaml.safe_load(fh) or {}
        # Products
        for prod in spec.get("products", []) or []:
            pid = str(prod.get("id", ""))
            for g in prod.get("groups", []) or []:
                gid = f"{pid}.{g.get('key', '')}"
                cid = str(g.get("chat_id", "")).strip()
                if cid:
                    catalog[gid] = cid
        # Cross-product
        for g in spec.get("cross_product", []) or []:
            gid = f"cross.{g.get('key', '')}"
            cid = str(g.get("chat_id", "")).strip()
            if cid:
                catalog[gid] = cid
    except Exception as e:
        logger.warning("[telegram_egress] spec load failed: %s", e)
    _GROUP_CATALOG = catalog
    return catalog


def resolve_chat_id(group_id: str) -> str | None:
    """Resolve a group_id (e.g. 'owner_alerts' or 'marketing.announcements') to chat_id.

    Supports:
      - Exact match: 'owner_alerts' → catalog lookup
      - Cross-product shorthand: 'owner_alerts' → 'cross.owner_alerts'
      - Full qualified: 'marketing.announcements' → catalog lookup
    """
    catalog = _load_group_catalog()
    # Exact match
    if group_id in catalog:
        return catalog[group_id]
    # Cross-product shorthand (e.g. 'owner_alerts' → 'cross.owner_alerts')
    cross_key = f"cross.{group_id}"
    if cross_key in catalog:
        return catalog[cross_key]
    # Direct chat_id passthrough (if someone passes a numeric chat_id)
    stripped = group_id.strip()
    if stripped.lstrip("-").isdigit():
        return stripped
    return None


async def _send_via_bot_api(
    chat_id: str,
    method: str,
    payload: dict[str, Any],
    timeout_s: float = _TIMEOUT_S,
) -> dict[str, Any]:
    """Low-level Telegram Bot API call. Never raises.

    Tries each configured egress token in priority order; a token that
    returns 401 Unauthorized is blacklisted for this process and the next
    candidate is tried, so one revoked token cannot kill all egress.
    """
    import httpx

    candidates = _token_candidates()
    if not candidates:
        return {"sent": False, "error": "no_bot_token"}

    last_error = "unknown"
    for token in candidates:
        try:
            url = f"https://api.telegram.org/bot{token}/{method}"
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(url, json=payload)
                body = resp.json() if resp.status_code == 200 else {
                    "ok": False,
                    "error_code": resp.status_code,
                    "description": resp.text[:500],
                }
                if body.get("ok"):
                    return {
                        "sent": True,
                        "message_id": body.get("result", {}).get("message_id"),
                        "chat_id": chat_id,
                    }
                err_code = body.get("error_code")
                desc = str(body.get("description", "unknown"))
                last_error = desc[:200]
                if err_code == 401:
                    # Revoked/dead token — blacklist and try the next candidate
                    logger.warning(
                        "[telegram_egress] token 401 Unauthorized — blacklisting this token and falling back (chat=%s)",
                        chat_id,
                    )
                    _dead_tokens.add(token)
                    continue
                logger.warning(
                    "[telegram_egress] API error %s: %s (chat=%s)",
                    err_code,
                    desc,
                    chat_id,
                )
                # Non-401 errors (bad chat, rate limit) won't be fixed by another token
                return {"sent": False, "error": last_error}
        except asyncio.TimeoutError:
            last_error = "timeout"
        except Exception as e:
            logger.warning("[telegram_egress] send failed: %s", e)
            last_error = str(e)[:200]
    return {"sent": False, "error": last_error}


def _truncate(text: str, limit: int) -> str:
    """Truncate text to limit, appending '…' if cut."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def send_to_group(
    group_id: str,
    text: str,
    *,
    thread_id: int | None = None,
    parse_mode: str | None = None,
    disable_preview: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send a text message to a Telegram group. Never raises.

    Args:
        group_id: e.g. 'owner_alerts', 'marketing.announcements', 'cross.ops'
        text: Message text (truncated to 4096 chars)
        thread_id: Forum topic thread ID (optional)
        parse_mode: 'HTML' or 'Markdown' (optional)
        disable_preview: Suppress link previews (default True)
        dry_run: If True, return the payload without sending

    Returns:
        {"sent": bool, "message_id": int|None, "error": str|None}
    """
    chat_id = resolve_chat_id(group_id)
    if not chat_id:
        return {"sent": False, "error": f"unknown_group:{group_id}"}
    if not text or not text.strip():
        return {"sent": False, "error": "empty_text"}

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": _truncate(text.strip(), _TEXT_MAX),
        "disable_web_page_preview": disable_preview,
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    if parse_mode:
        payload["parse_mode"] = parse_mode

    if dry_run:
        return {"sent": False, "dry_run": True, "payload": payload}

    result = await _send_via_bot_api(chat_id, "sendMessage", payload)
    try:
        from app.utils import owner_feed

        owner_feed.emit(
            source="telegram_egress",
            actor="system",
            text=f"TG send {'OK' if result.get('sent') else 'FAIL'}: {group_id} ({result.get('error', 'ok')})",
            severity="info" if result.get("sent") else "P1",
            kind="done" if result.get("sent") else "blocked",
        )
    except Exception:
        pass
    await asyncio.sleep(_RATE_LIMIT_DELAY_S)
    return result


async def send_video_to_group(
    group_id: str,
    video: bytes | str,
    *,
    caption: str = "",
    thread_id: int | None = None,
    filename: str = "video.mp4",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send a video to a Telegram group. Never raises.

    Args:
        group_id: e.g. 'cross.owner_alerts'
        video: Video bytes or file path
        caption: Caption text (truncated to 1024 chars)
        thread_id: Forum topic thread ID (optional)
        filename: Filename for the video attachment
        dry_run: If True, return the payload without sending

    Returns:
        {"sent": bool, "message_id": int|None, "error": str|None}
    """
    chat_id = resolve_chat_id(group_id)
    if not chat_id:
        return {"sent": False, "error": f"unknown_group:{group_id}"}

    token = _bot_token()
    if not token:
        return {"sent": False, "error": "no_bot_token"}

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "caption": _truncate(caption, _CAPTION_MAX) if caption else "",
    }
    if thread_id:
        payload["message_thread_id"] = thread_id

    if dry_run:
        return {"sent": False, "dry_run": True, "payload": payload}

    try:
        import httpx

        url = f"https://api.telegram.org/bot{token}/sendVideo"
        # Prepare video as multipart upload
        if isinstance(video, (bytes, bytearray)):
            files = {"video": (filename, video, "video/mp4")}
        elif isinstance(video, (str, Path)):
            path = Path(video)
            if not path.exists():
                return {"sent": False, "error": "file_not_found"}
            files = {"video": (filename, path.read_bytes(), "video/mp4")}
        else:
            return {"sent": False, "error": "invalid_video_type"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, data=payload, files=files)
            body = resp.json() if resp.status_code == 200 else {
                "ok": False,
                "error_code": resp.status_code,
                "description": resp.text[:500],
            }
            if body.get("ok"):
                return {
                    "sent": True,
                    "message_id": body.get("result", {}).get("message_id"),
                    "chat_id": chat_id,
                }
            else:
                desc = body.get("description", "unknown")
                logger.warning(
                    "[telegram_egress] video API error %s: %s (chat=%s)",
                    body.get("error_code"),
                    desc,
                    chat_id,
                )
                return {"sent": False, "error": str(desc)[:200]}
    except asyncio.TimeoutError:
        return {"sent": False, "error": "timeout"}
    except Exception as e:
        logger.warning("[telegram_egress] video send failed: %s", e)
        return {"sent": False, "error": str(e)[:200]}


async def send_photo_to_group(
    group_id: str,
    photo: bytes | str,
    *,
    caption: str = "",
    thread_id: int | None = None,
    filename: str = "photo.jpg",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send a photo to a Telegram group. Never raises."""
    chat_id = resolve_chat_id(group_id)
    if not chat_id:
        return {"sent": False, "error": f"unknown_group:{group_id}"}
    token = _bot_token()
    if not token:
        return {"sent": False, "error": "no_bot_token"}

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "caption": _truncate(caption, _CAPTION_MAX) if caption else "",
    }
    if thread_id:
        payload["message_thread_id"] = thread_id

    if dry_run:
        return {"sent": False, "dry_run": True, "payload": payload}

    try:
        import httpx

        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        if isinstance(photo, (bytes, bytearray)):
            files = {"photo": (filename, photo, "image/jpeg")}
        elif isinstance(photo, (str, Path)):
            path = Path(photo)
            if not path.exists():
                return {"sent": False, "error": "file_not_found"}
            files = {"photo": (filename, path.read_bytes(), "image/jpeg")}
        else:
            return {"sent": False, "error": "invalid_photo_type"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, data=payload, files=files)
            body = resp.json() if resp.status_code == 200 else {
                "ok": False,
                "error_code": resp.status_code,
                "description": resp.text[:500],
            }
            if body.get("ok"):
                return {
                    "sent": True,
                    "message_id": body.get("result", {}).get("message_id"),
                    "chat_id": chat_id,
                }
            else:
                return {"sent": False, "error": str(body.get("description", ""))[:200]}
    except asyncio.TimeoutError:
        return {"sent": False, "error": "timeout"}
    except Exception as e:
        return {"sent": False, "error": str(e)[:200]}


def get_group_catalog() -> dict[str, str]:
    """Return the full group catalog (group_id → chat_id). For admin dashboards."""
    return dict(_load_group_catalog())


__all__ = [
    "send_to_group",
    "send_video_to_group",
    "send_photo_to_group",
    "resolve_chat_id",
    "get_group_catalog",
]
