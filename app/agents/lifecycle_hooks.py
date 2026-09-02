"""Agent lifecycle event hooks — Hermes/Ruflo-style pre/post task hooks.

Hermes (and Ruflo) jaise agent-frameworks user ko deti hain ki agent ke task
lifecycle pe (pre_task / post_task / on_error) custom side-effects fire ho — log,
phone-push, ya webhook. Yahi capability is project me deta hai: admin/agent data
file me hooks define kare, code-deploy ke bina (skill_pack ki tarah data-driven).

Design (project patterns):
  - Data file `data/agent_hooks.json`: list of
        {event, name, type:"log"|"ntfy"|"webhook", target?}
    event ∈ {pre_task, post_task, on_error}.
  - `fire(event, payload)` matching hooks chalata:
        * "log"     → logger.info (zero dep).
        * "ntfy"    → lazy httpx POST to target (ntfy topic URL), bounded.
        * "webhook" → lazy httpx POST json to target, bounded.
    Har network hook `asyncio.wait_for(..., 8)` se bounded — koi hook kabhi
    pipeline ko block/raise nahi karta (best-effort, never-raise — voice-deadair
    lesson: HAR await bounded).
  - `enabled()` sirf AUTO-firing ko gate karta (loops `fire()` call karenge);
    `register`/`list_hooks` flag-independent (admin manage kar sake).

Flag: AGENT_HOOKS=1
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DATA_FILE = os.path.join("data", "agent_hooks.json")
_EVENTS = ("pre_task", "post_task", "on_error")
_TYPES = ("log", "ntfy", "webhook")
_HTTP_TIMEOUT_S = 8


def enabled() -> bool:
    """Gates AUTOMATIC firing by loops. register/list flag-independent."""
    return (os.getenv("AGENT_HOOKS") or "").strip().lower() in ("1", "true", "yes")


def _load() -> list[dict[str, Any]]:
    """Read hooks list. Never raises; missing/corrupt → []."""
    try:
        if not os.path.isfile(_DATA_FILE):
            return []
        with open(_DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug(f"lifecycle_hooks load failed: {e}")
        return []


def _save(hooks: list[dict[str, Any]]) -> bool:
    try:
        os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(hooks, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.warning(f"lifecycle_hooks save failed: {e}")
        return False


def _is_safe_target(url: str) -> tuple[bool, str]:
    """SSRF guard — reject non-http(s), internal docker hostnames, and private/
    loopback/link-local/reserved/multicast IPs so a hook target can't probe our own
    infra or cloud-metadata (169.254.169.254). ALWAYS enforced (not flag-gated).
    Never raises. Mirrors customer_webhooks._is_url_safe."""
    try:
        import ipaddress
        import socket
        from urllib.parse import urlparse

        p = urlparse(url or "")
        if p.scheme not in {"http", "https"}:
            return False, "scheme_not_http(s)"
        host = (p.hostname or "").strip().lower()
        if not host:
            return False, "no_host"
        if host in {
            "localhost",
            "leadgen_app",
            "leadgen_db",
            "leadgen_redis",
            "leadgen_redis_cache",
            "pgbouncer",
            "qdrant",
            "redis",
            "redis-cache",
            "postgres",
            "tempo",
            "loki",
            "prometheus",
            "grafana",
            "alertmanager",
        }:
            return False, "internal_hostname"
        for entry in socket.getaddrinfo(host, None):
            try:
                ip = ipaddress.ip_address(entry[4][0])
            except Exception:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return False, f"private_ip:{ip}"
        return True, ""
    except Exception as e:
        return False, f"resolve_failed:{str(e)[:60]}"


def register(event: str, name: str, type: str, target: str = "") -> dict[str, Any]:
    """Naya hook add karo (append to json). Validated, never-raises."""
    ev = (event or "").strip().lower()
    nm = (name or "").strip()
    tp = (type or "").strip().lower()
    tg = (target or "").strip()
    if ev not in _EVENTS:
        return {"ok": False, "error": f"event must be one of {list(_EVENTS)}"}
    if not nm:
        return {"ok": False, "error": "name required"}
    if tp not in _TYPES:
        return {"ok": False, "error": f"type must be one of {list(_TYPES)}"}
    if tp in ("ntfy", "webhook"):
        if not tg:
            return {"ok": False, "error": f"target (URL) required for type '{tp}'"}
        ok_url, why = _is_safe_target(tg)
        if not ok_url:
            return {"ok": False, "error": f"unsafe target URL ({why})"}
    try:
        hooks = _load()
        hooks.append({"event": ev, "name": nm, "type": tp, "target": tg})
        if not _save(hooks):
            return {"ok": False, "error": "save failed"}
        logger.info(f"lifecycle_hooks: registered {ev} hook '{nm}' ({tp})")
        return {"ok": True, "event": ev, "name": nm, "type": tp, "target": tg}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def list_hooks() -> dict[str, Any]:
    """Saare hooks + meta (auto-firing on/off)."""
    return {"enabled": enabled(), "events": list(_EVENTS), "hooks": _load()}


async def _post(url: str, payload: dict[str, Any]) -> bool:
    """Bounded best-effort POST (lazy httpx). Never raises.

    SSRF re-check at fire-time (defense-in-depth: a hook may have been stored before
    the guard, or DNS may now resolve internal). Redirects disabled so an external
    target can't 302 into the private range.
    """
    try:
        safe, why = await asyncio.to_thread(_is_safe_target, url)
        if not safe:
            logger.warning(f"lifecycle_hooks blocked unsafe target ({why}): {url}")
            return False

        import httpx

        async def _do() -> bool:
            async with httpx.AsyncClient(follow_redirects=False) as client:
                await client.post(url, json=payload)
            return True

        return await asyncio.wait_for(_do(), timeout=_HTTP_TIMEOUT_S)
    except Exception as e:
        logger.debug(f"lifecycle_hooks POST failed ({url}): {e}")
        return False


async def fire(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Matching hooks fire karo (best-effort). Never raises.

    Returns {ok, event, fired, results:[{name,type,ok}]}. Har network hook
    8s pe bounded — koi bhi hook caller ko block/girne nahi deta.
    """
    ev = (event or "").strip().lower()
    pl = payload if isinstance(payload, dict) else {}
    results: list[dict[str, Any]] = []
    try:
        for h in _load():
            if (h.get("event") or "").strip().lower() != ev:
                continue
            tp = (h.get("type") or "").strip().lower()
            nm = h.get("name") or ""
            tg = (h.get("target") or "").strip()
            ok = False
            try:
                if tp == "log":
                    logger.info(f"[hook:{nm}] {ev}: {json.dumps(pl, ensure_ascii=False)[:500]}")
                    ok = True
                elif tp == "ntfy":
                    # ntfy expects raw message body; reuse json POST (ntfy accepts it).
                    ok = await _post(tg, {"event": ev, **pl}) if tg else False
                elif tp == "webhook":
                    ok = await _post(tg, {"event": ev, "payload": pl}) if tg else False
            except Exception as e:
                logger.debug(f"lifecycle_hooks fire '{nm}' failed: {e}")
                ok = False
            results.append({"name": nm, "type": tp, "ok": ok})
        return {"ok": True, "event": ev, "fired": len(results), "results": results}
    except Exception as e:
        logger.debug(f"lifecycle_hooks fire() failed: {e}")
        return {"ok": False, "event": ev, "fired": 0, "results": results, "error": str(e)[:200]}


__all__ = ["enabled", "register", "list_hooks", "fire"]
