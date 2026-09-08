"""Self-hosted ntfy push notifications (FREE — phone pe instant alert).

Email alerts (NOTIFY_EMAIL) ka complement: critical events Sumit ke phone pe
turant pahunchte (ntfy Android/iOS app → topic subscribe). Self-hosted container
`deploy/compose/docker-compose.tools.yml` me; phone ke liye Caddy se `ntfy.leadsgenai.in` expose.

GATED: `NTFY_URL` (publish URL, e.g. http://ntfy:80 in-network) + `NTFY_TOPIC`.
Optional `NTFY_TOKEN` (auth). Unset = inert no-op. NEVER raises — alerts kabhi
main flow nahi todte.

Use:
    from app.integrations import ntfy
    await ntfy.push("Payment aaya 💰", "Sharma Solar — ₹2,999 Growth plan", priority="high")
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_TIMEOUT = 6.0


def enabled() -> bool:
    return bool(os.environ.get("NTFY_URL", "").strip() and os.environ.get("NTFY_TOPIC", "").strip())


_PRIORITY_NUM = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}


async def push(
    title: str,
    message: str,
    priority: str = "default",
    tags: list[str] | None = None,
    actions: list[dict] | None = None,
) -> bool:
    """Send push notification. False on failure/disabled (best-effort, never raises).

    priority: min|low|default|high|urgent (ntfy levels).
    actions: optional tap-buttons in the notification itself (max 3, ntfy limit),
        e.g. [{"action": "view", "label": "Reply", "url": "https://wa.me/..."},
              {"action": "http", "label": "Done", "url": "https://.../quick-done/TOK",
               "method": "POST", "clear": True}]
        When set, publishes via ntfy's JSON API instead of the plain-text/header
        form — avoids comma/emoji escaping issues in header-encoded actions.
    """
    url = os.environ.get("NTFY_URL", "").strip().rstrip("/")
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not url or not topic:
        return False
    pr = priority if priority in _PRIORITY_NUM else "default"
    try:
        import httpx

        token = os.environ.get("NTFY_TOKEN", "").strip()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if actions:
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                payload = {
                    "topic": topic,
                    "title": (title or "LeadGen AI")[:200],
                    "message": (message or "")[:2000],
                    "priority": _PRIORITY_NUM[pr],
                    "tags": [str(t) for t in tags[:5]] if tags else [],
                    "actions": actions[:3],
                }
                r = await client.post(url + "/", json=payload, headers=headers)
            else:
                # Header-safe title: emoji ascii-strip ke baad bacha LEADING SPACE
                # ya newline httpx "Illegal header value" deta tha → alert silently
                # DROP (live 2026-07-06: " Boot-grace skip:..."). Whitespace collapse.
                _t = (title or "LeadGen AI").encode("ascii", "ignore").decode()
                _t = " ".join(_t.split()) or "LeadGen AI"
                headers = {"Title": _t, "Priority": pr}
                if tags:
                    _tg = ",".join(" ".join(str(t).split()) for t in tags[:5]).strip(", ")
                    if _tg:
                        headers["Tags"] = _tg
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                r = await client.post(
                    f"{url}/{topic}", content=(message or "")[:2000], headers=headers
                )
            return r.status_code in (200, 201)
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("ntfy push failed: %s", exc)
        return False


def push_bg(
    title: str,
    message: str,
    priority: str = "default",
    tags: list[str] | None = None,
    actions: list[dict] | None = None,
) -> None:
    """Fire-and-forget from async context (task create; sync context = skip)."""
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        loop.create_task(push(title, message, priority=priority, tags=tags, actions=actions))
    except Exception:
        pass


__all__ = ["push", "push_bg", "enabled"]
