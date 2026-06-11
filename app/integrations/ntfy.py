"""Self-hosted ntfy push notifications (FREE — phone pe instant alert).

Email alerts (NOTIFY_EMAIL) ka complement: critical events Sumit ke phone pe
turant pahunchte (ntfy Android/iOS app → topic subscribe). Self-hosted container
`docker-compose.tools.yml` me; phone ke liye Caddy se `ntfy.leadsgenai.in` expose.

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


async def push(
    title: str,
    message: str,
    priority: str = "default",
    tags: list[str] | None = None,
) -> bool:
    """Send push notification. False on failure/disabled (best-effort, never raises).

    priority: min|low|default|high|urgent (ntfy levels).
    """
    url = os.environ.get("NTFY_URL", "").strip().rstrip("/")
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not url or not topic:
        return False
    try:
        import httpx

        headers = {
            "Title": (title or "LeadGen AI").encode("ascii", "ignore").decode() or "LeadGen AI",
            "Priority": priority if priority in ("min", "low", "default", "high", "urgent") else "default",
        }
        if tags:
            headers["Tags"] = ",".join(str(t) for t in tags[:5])
        token = os.environ.get("NTFY_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(f"{url}/{topic}", content=(message or "")[:2000], headers=headers)
            return r.status_code in (200, 201)
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("ntfy push failed: %s", exc)
        return False


def push_bg(title: str, message: str, priority: str = "default", tags: list[str] | None = None) -> None:
    """Fire-and-forget from async context (task create; sync context = skip)."""
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        loop.create_task(push(title, message, priority=priority, tags=tags))
    except Exception:
        pass


__all__ = ["push", "push_bg", "enabled"]
