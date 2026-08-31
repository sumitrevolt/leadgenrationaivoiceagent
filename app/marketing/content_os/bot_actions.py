"""
content_os.bot_actions — Tiny handler table that maps legacy Telegram callbacks
+ 'app content approve <asset_id>' style owner inputs to the public /api/content-os
routes. Useful for any external bot (Hermes / openclaw / ntfy action button)
to drive the daily video queue.
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def list_pending_for_owner(limit: int = 10) -> list[dict]:
    try:
        from app.marketing.content_os.inbox_watcher import list_pending
        return list_pending(limit=limit)
    except Exception as e:
        logger.warning("[content_os.bot_actions] list_pending failed: %s", e)
        return []


def handle_owner_command(text: str) -> str:
    """
    Pure-string parser. Examples the owner can type in chat:
       "content pending"            -> list pending
       "content approve 5"          -> approve asset #5 in the most recent pending list
       "content recreate 5 hook change"
       "content skip 5"
       "content run"                -> force daily run
       "content run-for acme"       -> one-client trigger
    Returns a human-friendly string.
    """
    if not text or not text.strip().lower().startswith("content"):
        return ""
    parts = text.strip().split(maxsplit=2)
    if len(parts) < 2:
        return "Try: content pending | content approve N | content recreate N ... | content run | content run-for <slug>"

    sub = parts[1].lower()
    if sub == "pending":
        items = list_pending_for_owner()
        if not items:
            return "[content_os] queue empty — looks good."
        lines = [f"[content_os] {len(items)} pending:"]
        for i, it in enumerate(items[:10], 1):
            lines.append(f"  {i}. {it.get('title','?')[:40]} — {it.get('id')}")
        lines.append("\nReply `content approve N` / `recreate N ...` / `skip N`.")
        return "\n".join(lines)

    if sub in {"approve", "recreate", "skip"} and len(parts) >= 3:
        try:
            idx = int(parts[2].split()[0]) - 1
        except Exception:
            return "Bad index — `content approve 1`"
        items = list_pending_for_owner()
        if not (0 <= idx < len(items)):
            return "Index out of range."
        asset_id = items[idx]["id"]
        feedback = " ".join(parts[2].split()[1:]) if sub == "recreate" else None
        try:
            from app.api.internal_media import approve as _approve_endpoint  # type: ignore
            from pydantic import BaseModel  # noqa
            # call internal helper directly
            from app.marketing.content_os.inbox_watcher import (
                approve as _approve_act, recreate as _recreate_act, skip as _skip_act,
            )
            if sub == "approve":
                res = _approve_act(asset_id)
            elif sub == "recreate":
                res = _recreate_act(asset_id, feedback or "")
            else:
                res = _skip_act(asset_id)
            return f"[content_os] {sub} → {res}"
        except Exception as e:
            return f"[content_os] failed: {e}"

    if sub == "run":
        try:
            from app.marketing.content_os.engine import daily_video_run
            return f"[content_os] {daily_video_run(force=True)}"
        except Exception as e:
            return f"[content_os] run-now failed: {e}"

    if sub == "run-for" and len(parts) >= 3:
        slug = parts[2].strip()
        try:
            from app.marketing.content_os.engine import run_for_client
            return f"[content_os] {run_for_client(slug)}"
        except Exception as e:
            return f"[content_os] run-for failed: {e}"

    return "Unknown subcommand. Try: content pending | approve N | recreate N ... | skip N | run | run-for <slug>"
