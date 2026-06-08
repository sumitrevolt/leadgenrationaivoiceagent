"""Content scheduler — schedule posts for specific future dates (Buffer/Hootsuite-style).

`auto_content` daily content deta hai; yeh DATE-targeted scheduling deta hai — kisi khaas
din ke liye post queue karo (Diwali, anniversary, sale day). Roz ka sweep due items ko
auto-PREPARE karta hai (content generate → ready-to-post). Store: data/content_schedule.jsonl.

Never raises. Auto-publish nahi (Meta API blocked) — ready content 1-click human post ke liye.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_FILE = os.path.join("data", "content_schedule.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read() -> list[dict]:
    out: list[dict] = []
    try:
        if os.path.exists(_FILE):
            with open(_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out


def _write_all(items: list[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(_FILE), exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.info("content_schedule write err: %s", e)


def schedule(
    business_name: str,
    niche: str = "general",
    date_iso: str = "",
    occasion: str = "",
    offer: str = "",
    channel: str = "instagram",
    client_id: str = "",
) -> dict[str, Any]:
    """Schedule a post for a date (YYYY-MM-DD). Returns the created item."""
    item = {
        "id": uuid.uuid4().hex[:8],
        "business_name": (business_name or "").strip() or "Aapka Business",
        "niche": (niche or "general").strip(),
        "date": (date_iso or date.today().isoformat()).strip()[:10],
        "occasion": (occasion or "").strip(),
        "offer": (offer or "").strip(),
        "channel": (channel or "instagram").strip(),
        "client_id": (client_id or "").strip(),
        "status": "scheduled",
        "content": None,
        "created_at": _now(),
    }
    items = _read()
    items.append(item)
    _write_all(items)
    return item


def list_scheduled(status: str | None = None, limit: int = 200) -> list[dict]:
    items = _read()
    if status:
        items = [i for i in items if i.get("status") == status]
    items.sort(key=lambda i: i.get("date", ""))
    return items[:limit]


def mark(item_id: str, status: str) -> bool:
    items = _read()
    hit = False
    for i in items:
        if i.get("id") == item_id:
            i["status"] = status
            hit = True
    if hit:
        _write_all(items)
    return hit


async def run_due(limit: int = 20) -> dict[str, Any]:
    """Prepare content for items due today or earlier (status=scheduled). Never raises."""
    res = {"due": 0, "prepared": 0}
    try:
        today = date.today().isoformat()
        items = _read()
        due = [i for i in items if i.get("status") == "scheduled" and (i.get("date", "") <= today)]
        res["due"] = len(due)
        if not due:
            return res
        from app.marketing import post_generator

        for i in due[: max(1, limit)]:
            try:
                post = await post_generator.generate_post(
                    business_name=i.get("business_name", ""),
                    niche=i.get("niche", "general"),
                    occasion=i.get("occasion", ""),
                    offer=i.get("offer", ""),
                )
                i["content"] = {
                    "caption": post.get("caption", ""),
                    "hashtags": post.get("hashtags", []),
                    "image_idea": post.get("image_idea", ""),
                }
                i["status"] = "ready"
                i["prepared_at"] = _now()
                res["prepared"] += 1
            except Exception as e:
                logger.info("schedule prepare err: %s", e)
        _write_all(items)
        try:
            from app.platform.team import log_event

            log_event("isha", "content_scheduled", f"{res['prepared']} posts prepared (of {res['due']} due)")
        except Exception:
            pass
        return res
    except Exception as e:
        logger.info("run_due err: %s", e)
        return res


__all__ = ["schedule", "list_scheduled", "mark", "run_due"]
