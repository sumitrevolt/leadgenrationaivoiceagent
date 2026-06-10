"""Outbound webhooks (Zapier/HighLevel-pattern) — events ko client systems tak pohchao.

Client (ya khud Sumit) apna webhook URL register kare → naya lead/inquiry/signup
hote hi HMAC-signed JSON POST. Isse koi bhi external system (Google Sheets via
Apps Script, n8n, Zapier, client ka CRM) bina humse pooche integrate ho jata.

Fire-and-forget, 5s timeout, kabhi raise nahi, retries nahi (receiver idempotent
rakhe). Store: data/outbound_webhooks.jsonl (configs) + webhook_deliveries.jsonl
(last 500 results). Koi gate nahi — bina registered URL ke inert.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "outbound_webhooks.jsonl")
_DELIVERIES = os.path.join("data", "webhook_deliveries.jsonl")
EVENTS = ["inquiry_received", "signup", "lead_hot", "booking", "payment_failed", "review_new"]


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


def register(url: str, events: list[str] | None = None, client_id: str = "", secret: str = "") -> dict[str, Any]:
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
        return {"ok": True, "webhook": {k: v for k, v in rec.items() if k != "secret"}, "secret": rec["secret"]}
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
            if r.get("active") and event in (r.get("events") or [])
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
        async with httpx.AsyncClient() as client:
            for h in hooks:
                try:
                    sig = hmac.new(str(h.get("secret", "")).encode(), body.encode(), hashlib.sha256).hexdigest()
                    resp = await client.post(
                        h["url"],
                        content=body,
                        headers={"Content-Type": "application/json", "X-LeadsGenAI-Signature": sig},
                        timeout=5.0,
                    )
                    ok = 200 <= resp.status_code < 300
                    delivered += 1 if ok else 0
                    _log_delivery(h, event, resp.status_code)
                except Exception as e:
                    _log_delivery(h, event, 0, str(e)[:120])
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
