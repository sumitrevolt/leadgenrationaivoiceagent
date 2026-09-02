"""Allowlisted HTTP node for Flow Runner Phase 5.

Admin-only (enforced at API layer), GET/POST only, host-allowlist (env),
timeout-bounded, SSRF-guarded (no private IPs), NEVER raises, NO secrets.
Cannot reach telephony/WhatsApp/email-provider hosts (they are never on the
allowlist + there is no secret interpolation to authenticate to them).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from urllib.parse import urlparse

_ALLOWLIST_ENV = "FLOW_HTTP_ALLOWLIST"  # comma/space/newline-separated host suffixes
_TIMEOUT_S = 8.0
_MAX_BODY = 200_000  # response truncation cap (chars)


def _allowlist() -> list[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, "")
    return [h.strip().lower().lstrip(".") for h in re.split(r"[,\s]+", raw or "") if h.strip()]


def _host_allowed(host: str, allow: list[str]) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if not h or not allow:
        return False
    return any(h == a or h.endswith("." + a) for a in allow)


def _is_public(host: str) -> bool:
    """Block loopback/private/link-local/reserved (mirrors website_auditor idiom)."""
    low = (host or "").strip().lower().rstrip(".")
    if not low or low == "localhost" or low.endswith((".local", ".internal")):
        return False
    try:
        infos = socket.getaddrinfo(low, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        ip = str(info[4][0]).split("%")[0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False
    return True


async def run(inputs: dict) -> dict:
    """inputs: {url, method?('GET'|'POST'), json?(dict), headers?(SAFE static only)}.
    Returns {ok, count, detail} (Phase-1 executor contract). Never raises."""
    import asyncio

    try:
        url = str((inputs or {}).get("url", "")).strip()
        method = str((inputs or {}).get("method", "GET")).strip().upper()
        if method not in ("GET", "POST"):
            return {
                "ok": False,
                "count": 0,
                "detail": f"method {method} not allowed (GET/POST only)",
            }
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return {"ok": False, "count": 0, "detail": "url must be http(s) with a host"}
        allow = _allowlist()
        if not _host_allowed(p.hostname, allow):
            return {
                "ok": False,
                "count": 0,
                "detail": f"host '{p.hostname}' not in FLOW_HTTP_ALLOWLIST",
            }
        if not await asyncio.to_thread(_is_public, p.hostname):
            return {
                "ok": False,
                "count": 0,
                "detail": f"host '{p.hostname}' resolves to a private/blocked IP",
            }
        import httpx

        raw_hdrs = inputs.get("headers") if isinstance(inputs.get("headers"), dict) else {}
        headers = {
            str(k): str(v) for k, v in list(raw_hdrs.items())[:10]
        }  # static only, no secrets
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=False) as cx:
            if method == "GET":
                r = await cx.get(url, headers=headers)
            else:
                body = inputs.get("json") if isinstance(inputs.get("json"), (dict, list)) else None
                r = await cx.post(url, headers=headers, json=body)
        text = (r.text or "")[:_MAX_BODY]
        ok = 200 <= r.status_code < 400
        return {
            "ok": ok,
            "count": 1 if ok else 0,
            "detail": f"{method} {p.hostname} -> {r.status_code} ({len(text)}b)",
        }
    except Exception as e:
        return {"ok": False, "count": 0, "detail": f"http err: {str(e)[:120]}"}


__all__ = ["run"]
