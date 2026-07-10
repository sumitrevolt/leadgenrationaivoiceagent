"""Outbound webhooks (Zapier/HighLevel-pattern) — events ko client systems tak pohchao.

Client (ya khud Sumit) apna webhook URL register kare → naya lead/inquiry/signup
hote hi HMAC-signed JSON POST. Isse koi bhi external system (Google Sheets via
Apps Script, n8n, Zapier, client ka CRM) bina humse pooche integrate ho jata.

5s timeout, kabhi raise nahi. RELIABLE DELIVERY (outbox pattern — audit): transient
fail pe event LOSE nahi hota — retry-queue me jaata, background `retry_pending()`
exponential-backoff + jitter ke saath redeliver karta (at-least-once); max attempts
ke baad DLQ. Consumer-side idempotency (idempotency.py) ke saath = reliable + dedupe.
Store: outbound_webhooks.jsonl (configs) + webhook_deliveries.jsonl (last 500) +
webhook_retry_queue.jsonl (pending) + webhook_dlq.jsonl (dead). Bina URL ke inert.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "outbound_webhooks.jsonl")
_DELIVERIES = os.path.join("data", "webhook_deliveries.jsonl")
_RETRY = os.path.join("data", "webhook_retry_queue.jsonl")  # outbox: pending redeliveries
_DLQ = os.path.join("data", "webhook_dlq.jsonl")  # dead after max attempts
_MAX_ATTEMPTS = 6
_FLUSH_LOCK = asyncio.Lock()  # ek hi flush per-process (concurrent flush avoid)
# Strong refs to in-flight opportunistic flush tasks — asyncio only keeps a weak ref,
# so without this a fire-and-forget create_task() can be GC'd mid-run (lost retry flush).
_FLUSH_TASKS: set = set()
EVENTS = [
    "inquiry_received",
    "signup",
    "lead_hot",
    "booking",
    "payment_failed",
    "payment_captured",
    "call_completed",
    "review_new",
]


def _backoff_s(attempts: int) -> float:
    """Exponential backoff + jitter (best-practice): ~60s,4m,16m,1h,4h, cap 6h. ±25% jitter."""
    base = min(60.0 * (4 ** max(0, attempts - 1)), 21600.0)
    return base * (0.75 + random.random() * 0.5)


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _write_all(path: str, rows: list[dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def register(
    url: str, events: list[str] | None = None, client_id: str = "", secret: str = ""
) -> dict[str, Any]:
    """Webhook add/update (dedupe by url). https only. Kabhi raise nahi."""
    try:
        u = (url or "").strip()
        if not u.startswith("https://"):
            return {"ok": False, "error": "https URL required"}
        evs = [e for e in (events or EVENTS) if e in EVENTS] or EVENTS
        rows = _read(_STORE)
        for r in rows:
            if r.get("url") == u:
                r["events"], r["client_id"], r["active"] = evs, client_id, True
                if secret:
                    r["secret"] = secret
                _write_all(_STORE, rows)
                return {"ok": True, "webhook": {k: v for k, v in r.items() if k != "secret"}}
        rec = {
            "id": uuid.uuid4().hex[:10],
            "url": u,
            "events": evs,
            "client_id": str(client_id or ""),
            "secret": secret or uuid.uuid4().hex,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(rec)
        _write_all(_STORE, rows)
        return {
            "ok": True,
            "webhook": {k: v for k, v in rec.items() if k != "secret"},
            "secret": rec["secret"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_webhooks() -> list[dict[str, Any]]:
    return [{k: v for k, v in r.items() if k != "secret"} for r in _read(_STORE)]


def remove(webhook_id: str) -> bool:
    rows = _read(_STORE)
    new = [r for r in rows if r.get("id") != webhook_id]
    if len(new) != len(rows):
        _write_all(_STORE, new)
        return True
    return False


async def emit(event: str, payload: dict[str, Any], client_id: str = "") -> int:
    """Event fire karo — matching active webhooks pe signed POST. Kabhi raise nahi.
    Returns delivered count. Bina registered hooks = 0 (inert)."""
    delivered = 0
    try:
        hooks = [
            r
            for r in _read(_STORE)
            if r.get("active")
            and event in (r.get("events") or [])
            and (not r.get("client_id") or not client_id or r.get("client_id") == client_id)
        ]
        if not hooks:
            return 0
        import httpx

        body = json.dumps(
            {"event": event, "payload": payload, "at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
            default=str,
        )
        # Opportunistic outbox flush — naya event aaya to due retries bhi process karo
        # (non-blocking, single-flight via _FLUSH_LOCK). Scheduler-free reliability.
        try:
            _ft = asyncio.create_task(retry_pending())
            _FLUSH_TASKS.add(_ft)
            _ft.add_done_callback(_FLUSH_TASKS.discard)
        except Exception:
            pass
        async with httpx.AsyncClient(timeout=30.0) as client:
            for h in hooks:
                try:
                    sig = hmac.new(
                        str(h.get("secret", "")).encode(), body.encode(), hashlib.sha256
                    ).hexdigest()
                    resp = await client.post(
                        h["url"],
                        content=body,
                        headers={"Content-Type": "application/json", "X-LeadsGenAI-Signature": sig},
                        timeout=5.0,
                    )
                    ok = 200 <= resp.status_code < 300
                    delivered += 1 if ok else 0
                    _log_delivery(h, event, resp.status_code)
                    if not ok:  # transient/non-2xx → outbox retry (event lose na ho)
                        _enqueue_retry(h.get("id", ""), event, body, f"status {resp.status_code}")
                except Exception as e:
                    _log_delivery(h, event, 0, str(e)[:120])
                    _enqueue_retry(h.get("id", ""), event, body, str(e)[:120])
        return delivered
    except Exception as e:
        logger.debug(f"[webhooks] emit skip: {e}")
        return delivered


def _log_delivery(hook: dict[str, Any], event: str, status: int, err: str = "") -> None:
    try:
        rows = _read(_DELIVERIES)[-499:]
        rows.append(
            {
                "webhook_id": hook.get("id"),
                "url": str(hook.get("url", ""))[:120],
                "event": event,
                "status": status,
                "error": err,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_all(_DELIVERIES, rows)
    except Exception:
        pass


def recent_deliveries(limit: int = 30) -> list[dict[str, Any]]:
    return _read(_DELIVERIES)[-limit:][::-1]


def _enqueue_retry(hook_id: str, event: str, body: str, err: str) -> None:
    """Failed delivery → retry-queue (outbox). file_lock se safe. Never raises."""
    if not hook_id:
        return
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_RETRY):
            rows = _read(_RETRY)
            rows.append(
                {
                    "id": uuid.uuid4().hex[:10],
                    "webhook_id": hook_id,
                    "event": event,
                    "body": body,
                    "attempts": 1,
                    "next_at": time.time() + _backoff_s(1),
                    "last_error": (err or "")[:160],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _write_all(_RETRY, rows[-2000:])  # bounded
    except Exception:
        pass


async def retry_pending(max_items: int = 50) -> dict[str, Any]:
    """Outbox worker — due failed-deliveries ko backoff+jitter ke saath redeliver karo.
    Delivered/hook-gone → queue se hata; max attempts ke baad → DLQ. Concurrency-safe
    (single-flight _FLUSH_LOCK + reconcile-by-id taaki flush ke dauraan aaye naye items
    na khoyein). Never raises. Returns {retried, delivered, dlq, pending}."""
    res = {"retried": 0, "delivered": 0, "dlq": 0, "pending": 0}
    if _FLUSH_LOCK.locked():
        return res
    async with _FLUSH_LOCK:
        try:
            snapshot = _read(_RETRY)
        except Exception:
            return res
        if not snapshot:
            return res
        now = time.time()
        hooks = {h.get("id"): h for h in _read(_STORE)}
        done_ids: set[str] = set()  # delivered ya hook-gone → remove
        updates: dict[str, dict] = {}  # id → updated item (requeue with new next_at)
        dead: list[dict[str, Any]] = []  # → DLQ
        processed = 0
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                for item in snapshot:
                    iid = item.get("id", "")
                    if processed >= max_items or float(item.get("next_at", 0)) > now:
                        continue  # not due / budget over — snapshot me rahega
                    processed += 1
                    res["retried"] += 1
                    h = hooks.get(item.get("webhook_id"))
                    if not h or not h.get("active"):
                        done_ids.add(iid)  # hook gaya/inactive — drop
                        continue
                    try:
                        body = item.get("body") or ""
                        sig = hmac.new(
                            str(h.get("secret", "")).encode(), body.encode(), hashlib.sha256
                        ).hexdigest()
                        resp = await client.post(
                            h["url"],
                            content=body,
                            headers={
                                "Content-Type": "application/json",
                                "X-LeadsGenAI-Signature": sig,
                            },
                            timeout=5.0,
                        )
                        if 200 <= resp.status_code < 300:
                            res["delivered"] += 1
                            done_ids.add(iid)
                            _log_delivery(h, item.get("event", ""), resp.status_code)
                            continue
                        raise ValueError(f"status {resp.status_code}")
                    except Exception as e:
                        attempts = int(item.get("attempts", 1)) + 1
                        item["attempts"] = attempts
                        item["last_error"] = str(e)[:160]
                        if attempts > _MAX_ATTEMPTS:
                            done_ids.add(iid)
                            dead.append(item)
                            res["dlq"] += 1
                            _log_delivery(
                                h, item.get("event", ""), 0, f"DLQ after {attempts} attempts"
                            )
                        else:
                            item["next_at"] = now + _backoff_s(attempts)
                            updates[iid] = item
        except Exception:
            pass
        # Reconcile (flush ke dauraan emit ne naye items add kiye honge → re-read + merge).
        try:
            from app.utils.file_lock import file_lock

            with file_lock(_RETRY):
                current = _read(_RETRY)
                merged = [
                    updates.get(r.get("id", ""), r)
                    for r in current
                    if r.get("id", "") not in done_ids
                ]
                _write_all(_RETRY, merged[-2000:])
                res["pending"] = len(merged)
            if dead:
                d = _read(_DLQ)[-499:]
                d.extend(dead)
                _write_all(_DLQ, d)
        except Exception:
            pass
        return res


def dlq_recent(limit: int = 30) -> list[dict[str, Any]]:
    """Dead-lettered (max-attempts ke baad fail) deliveries — inspection/manual replay."""
    return _read(_DLQ)[-limit:][::-1]
