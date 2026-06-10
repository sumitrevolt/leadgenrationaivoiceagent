"""Telegram auto-publish — pehla TRUE auto-post channel (Bot API free + ToS-allowed).

Meta/GBP approval-blocked hain; Telegram pe client ke channel/group me daily content
AUTO publish ho sakta hai (bot ko admin banao, chat_id do).

GATED: `TELEGRAM_BOT_TOKEN` env (BotFather free). Bina token = inert ({"sent": False}).
Auto-scheduler wiring flag: `TELEGRAM_AUTO_PUBLISH=1` (default OFF; abhi API/manual).
Log: data/telegram_posts.jsonl. NEVER raises.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "telegram_posts.jsonl")
_API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def enabled() -> bool:
    return bool(_token())


def _log(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"telegram log failed: {e}")


async def send_post(chat_id: str, text: str, image_url: str = "") -> dict[str, Any]:
    """Channel/group me post bhejo. Token nahi = inert reason ke saath."""
    chat_id = (chat_id or "").strip()
    text = (text or "").strip()
    if not enabled():
        return {"sent": False, "reason": "TELEGRAM_BOT_TOKEN unset (BotFather se free banao)"}
    if not chat_id or not text:
        return {"sent": False, "reason": "chat_id/text missing"}
    try:
        import httpx

        token = _token()
        async with httpx.AsyncClient(timeout=10) as cx:
            if image_url:
                r = await cx.post(
                    _API.format(token=token, method="sendPhoto"),
                    json={"chat_id": chat_id, "photo": image_url, "caption": text[:1024]},
                )
            else:
                r = await cx.post(
                    _API.format(token=token, method="sendMessage"),
                    json={"chat_id": chat_id, "text": text[:4000]},
                )
        ok = r.status_code == 200 and r.json().get("ok")
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "chat_id": chat_id,
            "ok": bool(ok),
            "status": r.status_code,
            "len": len(text),
        }
        _log(rec)
        return {"sent": bool(ok), **({} if ok else {"reason": r.text[:200]})}
    except Exception as e:
        logger.warning(f"telegram send failed: {e}")
        return {"sent": False, "reason": str(e)[:150]}


async def send_for_client(client_id: str, occasion: str = "", offer: str = "") -> dict[str, Any]:
    """Client ka content generate karke uske telegram chat pe publish (chat_id client
    record ke `telegram_chat_id` field me — clients_store.update_client se set karo)."""
    from app.marketing import clients_store, post_generator

    client = clients_store.get_client(client_id) or {}
    chat_id = str(client.get("telegram_chat_id") or "").strip()
    if not chat_id:
        return {"sent": False, "reason": "client.telegram_chat_id unset"}
    post = await post_generator.generate_post(
        client.get("business_name") or "Business",
        niche=client.get("niche") or "general",
        occasion=occasion,
        offer=offer,
    )
    res = await send_post(chat_id, post.get("post_text") or post.get("caption", ""))
    return {**res, "caption": post.get("caption", "")}
