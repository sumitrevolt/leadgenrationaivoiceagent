"""webpush.py — OneSignal-killer web push (open Web-Push standard, NO paid svc).

Browser push notifications clients ki mini-sites/widgets se — pywebpush + VAPID
keys (env: VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, optional VAPID_CLAIM_EMAIL).
NO new dep auto-install: pywebpush ya keys ABSENT → poora module INERT
(available()={"ok":False}), send_push tab DRAFT-only record karta (jsonl).

Store: data/push_subs.jsonl (dedupe by endpoint) · data/push_drafts.jsonl.
sw.js me push listener MAIN SESSION add karega (yeh module sw.js NAHI chhoota).
NEVER raises, sab imports lazy.

VAPID keys generate (one-time, free):
    python -c "from py_vapid import Vapid01 as V; v=V(); v.generate_keys(); ..."
    ya: npx web-push generate-vapid-keys
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SUBS_FILE = os.path.join("data", "push_subs.jsonl")
_DRAFTS_FILE = os.path.join("data", "push_drafts.jsonl")
_SEND_CAP = 500  # ek send me max subscriptions


def vapid_public() -> str:
    return (os.getenv("VAPID_PUBLIC_KEY") or "").strip()


def _vapid_private() -> str:
    return (os.getenv("VAPID_PRIVATE_KEY") or "").strip()


def _claim_email() -> str:
    return (os.getenv("VAPID_CLAIM_EMAIL") or "admin@leadsgenai.in").strip()


def available() -> dict[str, Any]:
    """pywebpush import + dono VAPID keys present? Absent → inert (no install)."""
    have_keys = bool(vapid_public() and _vapid_private())
    have_lib = False
    try:
        import pywebpush  # noqa: F401

        have_lib = True
    except Exception:
        have_lib = False
    if have_lib and have_keys:
        return {"ok": True}
    return {
        "ok": False,
        "reason": "pywebpush_or_keys_missing",
        "pywebpush": have_lib,
        "vapid_keys": have_keys,
    }


# --------------------------------------------------------------------------- #
# Subscription store (jsonl, dedupe by endpoint)
# --------------------------------------------------------------------------- #
def _read(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
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


def _write_all(path: str, items: list[dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        content = "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items)
        try:
            from app.utils.file_lock import locked_rewrite

            if locked_rewrite(path, content):
                return
        except Exception:
            pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.debug(f"[webpush] write skip: {e}")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[webpush] append skip: {e}")


def save_subscription(slug: str, sub_json: dict[str, Any]) -> dict[str, Any]:
    """Browser PushSubscription save (dedupe endpoint). Never raises."""
    try:
        slug = (slug or "default").strip()[:64] or "default"
        if not isinstance(sub_json, dict):
            return {"ok": False, "error": "subscription must be an object"}
        endpoint = str(sub_json.get("endpoint") or "").strip()
        keys = sub_json.get("keys") or {}
        if not endpoint.startswith("https://") or not isinstance(keys, dict):
            return {"ok": False, "error": "invalid subscription (endpoint/keys)"}
        items = _read(_SUBS_FILE)
        if any(it.get("endpoint") == endpoint for it in items):
            return {"ok": True, "saved": False, "reason": "already_subscribed"}
        items.append(
            {
                "slug": slug,
                "endpoint": endpoint[:1000],
                "keys": {
                    "p256dh": str(keys.get("p256dh") or "")[:300],
                    "auth": str(keys.get("auth") or "")[:200],
                },
                "ts": time.time(),
            }
        )
        _write_all(_SUBS_FILE, items)
        return {
            "ok": True,
            "saved": True,
            "total_for_slug": sum(1 for i in items if i.get("slug") == slug),
        }
    except Exception as e:
        logger.debug(f"[webpush] save_subscription err: {e}")
        return {"ok": False, "error": str(e)[:160]}


def list_subs(slug: str | None = None) -> list[dict[str, Any]]:
    items = _read(_SUBS_FILE)
    if slug:
        items = [i for i in items if i.get("slug") == slug]
    return items


# --------------------------------------------------------------------------- #
# Send (available() pe REAL webpush; warna draft-record-only — inert)
# --------------------------------------------------------------------------- #
def send_push(slug: str, title: str, body: str, url: str = "") -> dict[str, Any]:
    """Slug ke saare subscribers ko push (cap 500, expired prune). Never raises.

    NOT available → draft record only (jab keys aayengi, dashboard se re-send).
    """
    slug = (slug or "default").strip()[:64] or "default"
    payload = {
        "title": (title or "Update").strip()[:120],
        "body": (body or "").strip()[:300],
        "url": (url or "https://leadsgenai.in").strip()[:500],
    }
    av = available()
    if not av.get("ok"):
        _append(_DRAFTS_FILE, {"ts": time.time(), "slug": slug, **payload, "status": "draft"})
        return {"ok": False, "reason": av.get("reason", "unavailable"), "draft_recorded": True}

    sent = failed = pruned = 0
    try:
        from pywebpush import WebPushException, webpush

        all_items = _read(_SUBS_FILE)
        targets = [i for i in all_items if i.get("slug") == slug][:_SEND_CAP]
        dead_endpoints: set[str] = set()
        data = json.dumps(payload, ensure_ascii=False)
        claims = {"sub": f"mailto:{_claim_email()}"}
        for sub in targets:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.get("endpoint"),
                        "keys": sub.get("keys") or {},
                    },
                    data=data,
                    vapid_private_key=_vapid_private(),
                    vapid_claims=dict(claims),
                    timeout=10,
                )
                sent += 1
            except WebPushException as e:
                failed += 1
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code in (404, 410):  # expired/gone — prune
                    dead_endpoints.add(str(sub.get("endpoint")))
            except Exception:
                failed += 1
        if dead_endpoints:
            pruned = len(dead_endpoints)
            _write_all(
                _SUBS_FILE,
                [i for i in all_items if str(i.get("endpoint")) not in dead_endpoints],
            )
    except Exception as e:
        logger.info(f"[webpush] send err: {e}")
        return {"ok": False, "error": str(e)[:160], "sent": sent, "failed": failed}
    try:
        from app.platform.team import log_event

        log_event("isha", "push_sent", f"{slug}: {sent} sent, {failed} failed, {pruned} pruned")
    except Exception:
        pass
    return {"ok": True, "sent": sent, "failed": failed, "pruned": pruned, "targets": sent + failed}


def status() -> dict[str, Any]:
    subs = _read(_SUBS_FILE)
    by_slug: dict[str, int] = {}
    for s in subs:
        k = str(s.get("slug") or "default")
        by_slug[k] = by_slug.get(k, 0) + 1
    return {
        "available": available(),
        "subscriptions": len(subs),
        "by_slug": by_slug,
        "drafts_pending": len(_read(_DRAFTS_FILE)),
        "vapid_public_set": bool(vapid_public()),
    }


# --------------------------------------------------------------------------- #
# Client JS snippet (vanilla) — mini-site/widget me inject karne ke liye
# --------------------------------------------------------------------------- #
def subscribe_js(slug: str) -> str:
    """Notification.requestPermission + pushManager.subscribe + POST sub.

    NOTE: kaam karne ke liye sw.js me push/notificationclick listeners chahiye
    (main session add karega — yeh module sw.js edit NAHI karta).
    """
    slug = (slug or "default").strip()[:64] or "default"
    pub = vapid_public()
    return (
        "(function(){\n"
        f"  var SLUG={json.dumps(slug)}, VAPID={json.dumps(pub)};\n"
        "  if(!VAPID||!('serviceWorker' in navigator)||!('PushManager' in window))return;\n"
        "  function b64ToU8(s){var p='='.repeat((4-s.length%4)%4);"
        "var b=(s+p).replace(/-/g,'+').replace(/_/g,'/');var r=atob(b);"
        "var a=new Uint8Array(r.length);for(var i=0;i<r.length;i++)a[i]=r.charCodeAt(i);return a;}\n"
        "  window.lgaiEnablePush=function(){\n"
        "    Notification.requestPermission().then(function(p){\n"
        "      if(p!=='granted')return;\n"
        "      navigator.serviceWorker.register('/sw.js').then(function(reg){\n"
        "        return reg.pushManager.subscribe({userVisibleOnly:true,"
        "applicationServerKey:b64ToU8(VAPID)});\n"
        "      }).then(function(sub){\n"
        "        return fetch('/api/contentauto/push/subscribe',{method:'POST',"
        "headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({slug:SLUG,subscription:sub.toJSON()})});\n"
        "      }).catch(function(e){console.warn('push subscribe failed',e);});\n"
        "    });\n"
        "  };\n"
        "})();\n"
    )


__all__ = [
    "available",
    "vapid_public",
    "save_subscription",
    "list_subs",
    "send_push",
    "status",
    "subscribe_js",
]
