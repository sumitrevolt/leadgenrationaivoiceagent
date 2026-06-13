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


def auto_enabled() -> bool:
    """Auto-publish loop gate. Token AUR TELEGRAM_AUTO_PUBLISH=1 dono chahiye —
    warna run_due() inert (zero behaviour change). Manual/API send isse independent."""
    return enabled() and os.getenv("TELEGRAM_AUTO_PUBLISH", "0").strip().lower() in ("1", "true", "yes")


_STATE = os.path.join("data", ".telegram_autopub.json")


def _load_state() -> dict[str, str]:
    try:
        with open(_STATE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_state(state: dict[str, str]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE) or ".", exist_ok=True)
        tmp = _STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, _STATE)
    except Exception as e:
        logger.warning(f"telegram autopub state save failed: {e}")


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
        try:
            from app.platform import integration_health

            if ok:
                integration_health.record_success("telegram")
            else:
                integration_health.record_failure("telegram", r.text[:150])
        except Exception:
            pass
        return {"sent": bool(ok), **({} if ok else {"reason": r.text[:200]})}
    except Exception as e:
        logger.warning(f"telegram send failed: {e}")
        try:
            from app.platform import integration_health

            integration_health.record_failure("telegram", str(e))
        except Exception:
            pass
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


async def run_due() -> dict[str, Any]:
    """Scheduler loop: TELEGRAM_AUTO_PUBLISH=1 pe har active client (jiska
    telegram_chat_id set hai) ke channel pe aaj ka content AUTO publish karo.
    Per-client daily dedupe (state file) — content-job din me ek baar chalta hai
    par re-run/double-tick pe dobara post na ho. Flag/token off = inert. NEVER raises."""
    if not auto_enabled():
        return {"ran": False, "reason": "TELEGRAM_AUTO_PUBLISH off ya token unset"}
    try:
        from app.marketing import clients_store

        day_key = time.strftime("%Y-%m-%d")
        state = _load_state()
        clients = clients_store.list_clients(status="active") or clients_store.list_clients()
        sent = skipped = failed = 0
        for c in clients:
            cid = str(c.get("id") or "").strip()
            chat_id = str(c.get("telegram_chat_id") or "").strip()
            if not cid or not chat_id:
                continue
            if state.get(cid) == day_key:  # already published today
                skipped += 1
                continue
            try:
                res = await send_for_client(cid)
                if res.get("sent"):
                    sent += 1
                    state[cid] = day_key  # mark only on success → retry next tick on failure
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.warning(f"telegram run_due client {cid} failed: {e}")
        _save_state(state)
        if sent:
            try:
                from app.platform import team

                team.log_event("isha", "telegram_autopublish", f"📣 Telegram auto-publish: {sent} clients")
            except Exception:
                pass
        return {"ran": True, "sent": sent, "skipped": skipped, "failed": failed}
    except Exception as e:
        logger.warning(f"telegram run_due failed: {e}")
        return {"ran": False, "reason": str(e)[:150]}
