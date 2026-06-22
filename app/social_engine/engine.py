"""social_engine.engine — enqueue + dispatch core. GATED `SOCIAL_ENGINE`.

  enqueue_publish(client_id, caption, media_path/url, platforms, account_refs) -> [job_ids]
  process_queue(limit) -> queued jobs claim -> provider dispatch -> published/retry/dead/skipped
Scheduler (run_cycle) AUR Celery task dono process_queue() call kar sakte (claim idempotent-ish).
NEVER raises.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

from . import store, vault
from .base import PublishRequest, PublishResult
from .providers import default_providers

logger = setup_logger(__name__)

_REGISTRY: dict[str, Any] | None = None


def registry() -> dict[str, Any]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = default_providers()
    return _REGISTRY


def enabled() -> bool:
    """Master gate. OFF = video_ad_cycle current inline path use karta (engine inert)."""
    return os.getenv("SOCIAL_ENGINE", "0").strip().lower() in ("1", "true", "yes")


def _resolve_account(client_id: str, platform: str, account_ref: str) -> dict[str, Any]:
    acct = vault.get(client_id, platform, account_ref) or {}
    if platform == "telegram" and not (acct.get("account_ref") or account_ref):
        try:
            from app.marketing import clients_store

            c = clients_store.get_client(client_id) or {}
            chat = str(c.get("telegram_chat_id") or "").strip()
            if chat:
                acct = {"token": "", "account_ref": chat, "meta": {}}
        except Exception:
            pass
    return acct


def _default_platforms(client_id: str) -> list[str]:
    """Sirf configured providers (telegram token / postiz / vault me jo accounts hain)."""
    out: list[str] = []
    reg = registry()
    try:
        if reg["telegram"].configured() and _resolve_account(client_id, "telegram", "").get("account_ref"):
            out.append("telegram")
        if reg["postiz"].configured():
            out.append("postiz")
        for a in vault.list_accounts(client_id):
            p = str(a.get("platform") or "")
            if p in reg and p not in out:
                out.append(p)
    except Exception as e:
        logger.debug(f"[engine] default_platforms skip: {e}")
    return out


def enqueue_publish(
    client_id: str,
    caption: str = "",
    media_path: str = "",
    media_url: str = "",
    media_type: str = "video",
    platforms: list[str] | None = None,
    account_refs: dict[str, str] | None = None,
) -> list[str]:
    """Ek post ko target platforms ke liye queue karo (1 job/platform). Returns job-ids."""
    try:
        plats = platforms or _default_platforms(client_id)
        refs = account_refs or {}
        ids: list[str] = []
        for p in plats:
            jid = store.enqueue(
                {
                    "client_id": client_id,
                    "platform": p,
                    "account_ref": refs.get(p, ""),
                    "media_type": media_type,
                    "media_path": media_path,
                    "media_url": media_url,
                    "caption": caption,
                }
            )
            if jid:
                ids.append(jid)
        # best-effort immediate Celery drain (no consumer = harmless; scheduler drains anyway)
        if ids:
            try:
                from .tasks import drain_social_queue

                if drain_social_queue is not None:
                    drain_social_queue.delay(len(ids) + 5)
            except Exception:
                pass
        return ids
    except Exception as e:
        logger.warning(f"[engine] enqueue_publish failed: {e}")
        return []


async def _dispatch_one(job: dict[str, Any]) -> PublishResult:
    p = str(job.get("platform") or "")
    prov = registry().get(p)
    if prov is None:
        return PublishResult(ok=False, platform=p, error="unknown platform")
    acct = _resolve_account(str(job.get("client_id") or ""), p, str(job.get("account_ref") or ""))
    if not prov.configured(acct):
        return PublishResult(ok=False, platform=p, error="__inert__")
    req = PublishRequest(
        client_id=str(job.get("client_id") or ""),
        caption=str(job.get("caption") or ""),
        media_path=str(job.get("media_path") or ""),
        media_url=str(job.get("media_url") or ""),
        media_type=str(job.get("media_type") or "video"),
        platform=p,
        account_ref=str(job.get("account_ref") or "") or str(acct.get("account_ref") or ""),
    )
    return await prov.publish(req, acct)


async def process_queue(limit: int = 20) -> dict[str, Any]:
    """Queued jobs drain karo. Scheduler/worker se. Flag off = inert."""
    if not enabled():
        return {"ran": False, "reason": "SOCIAL_ENGINE off"}
    published = retried = dead = skipped = 0
    try:
        jobs = store.claim_pending(limit)
        for job in jobs:
            jid = str(job.get("id") or "")
            try:
                res = await _dispatch_one(job)
            except Exception as e:
                res = PublishResult(ok=False, platform=str(job.get("platform") or ""), error=str(e)[:150])
            if res.ok:
                store.mark(jid, "published", post_id=res.post_id, post_url=res.url)
                published += 1
            elif res.error == "__inert__":
                store.mark(jid, "skipped", last_error="provider not configured")
                skipped += 1
            else:
                attempts = int(job.get("attempts") or 0) + 1
                if attempts >= store.max_attempts():
                    store.mark(jid, "dead", attempts=attempts, last_error=res.error)
                    dead += 1
                else:
                    store.mark(jid, "retry", attempts=attempts, last_error=res.error)
                    retried += 1
        return {"ran": True, "claimed": len(jobs), "published": published,
                "retried": retried, "dead": dead, "skipped": skipped}
    except Exception as e:
        logger.warning(f"[engine] process_queue failed: {e}")
        return {"ran": False, "reason": str(e)[:150]}
