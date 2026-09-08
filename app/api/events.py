"""
app/api/events.py — Real-time Server-Sent Events (SSE) endpoint.

GET /api/events/stream  → text/event-stream
  - Redis pub/sub channel "lgai:events" pe listen karta hai
  - Fallback: agar Redis unavailable ya in-memory cache hai, to DB se recent_events()
    poll karta hai (10s interval)
  - Heartbeat: 20s pe "ping" event (proxy timeouts prevent karta hai)
  - Admin-gated (require_admin dependency)

team.log_event() ab Redis PUBLISH bhi karta hai (non-blocking, fail-open).
Dashboard.EventSource('/api/events/stream') se live updates milenge bina 60s polling.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["Events"])

_CHANNEL = "lgai:events"
_HEARTBEAT_S = 20
_POLL_FALLBACK_S = 10  # jab Redis pub/sub nahi, DB poll interval


async def _redis_pubsub_stream(request: Request) -> AsyncGenerator[str, None]:
    """Redis pub/sub se live events → SSE format."""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
        pubsub = r.pubsub()
        await pubsub.subscribe(_CHANNEL)
        logger.info("[events] SSE client connected (Redis pub/sub)")

        last_heartbeat = time.monotonic()

        while True:
            # Client disconnect check
            if await request.is_disconnected():
                break

            # Non-blocking message check (timeout=0.5s)
            try:
                msg = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True), timeout=0.5
                )
            except asyncio.TimeoutError:
                msg = None
            except Exception:
                msg = None

            if msg and msg.get("type") == "message":
                data = msg.get("data", "")
                yield f"data: {data}\n\n"
                last_heartbeat = time.monotonic()  # real event = reset heartbeat timer

            # Heartbeat — proxy/nginx idle timeout prevent karo
            elif time.monotonic() - last_heartbeat > _HEARTBEAT_S:
                yield "event: ping\ndata: {}\n\n"
                last_heartbeat = time.monotonic()

            else:
                # CPU pe busy-loop nahi; pubsub.get_message already 0.5s wait karta
                await asyncio.sleep(0)

    except Exception as e:
        logger.debug(f"[events] pub/sub stream error: {e}")
    finally:
        try:
            await pubsub.unsubscribe(_CHANNEL)
            await r.aclose()
        except Exception:
            pass


async def _poll_fallback_stream(request: Request) -> AsyncGenerator[str, None]:
    """Fallback: har 10s DB se recent events poll karo (Redis nahi to)."""
    try:
        from app.platform.team import recent_events

        seen_ids: set[str] = set()
        last_heartbeat = time.monotonic()

        # Seed seen set with existing events (naye events hi bhejo)
        for ev in recent_events(limit=20):
            seen_ids.add(ev.get("id", ""))

        while True:
            if await request.is_disconnected():
                break

            await asyncio.sleep(_POLL_FALLBACK_S)

            try:
                events = recent_events(limit=30)
                new_events = [e for e in events if e.get("id", "") not in seen_ids]
                for ev in reversed(new_events):  # chronological order
                    eid = ev.get("id", "")
                    seen_ids.add(eid)
                    yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
                    last_heartbeat = time.monotonic()
            except Exception:
                pass

            if time.monotonic() - last_heartbeat > _HEARTBEAT_S:
                yield "event: ping\ndata: {}\n\n"
                last_heartbeat = time.monotonic()

    except Exception as e:
        logger.debug(f"[events] poll fallback error: {e}")


async def _sse_generator(request: Request) -> AsyncGenerator[str, None]:
    """Redis pub/sub try karo, fail → polling fallback."""
    use_redis = False
    try:
        from app.cache import _use_fallback  # type: ignore[attr-defined]

        use_redis = not _use_fallback
    except Exception:
        pass

    if use_redis:
        try:
            import redis.asyncio  # noqa: F401 — availability check

            async for chunk in _redis_pubsub_stream(request):
                yield chunk
            return
        except ImportError:
            pass

    # Fallback path
    async for chunk in _poll_fallback_stream(request):
        yield chunk


@router.get("/events/stream")
async def events_stream(request: Request, _user=Depends(require_admin)):
    """Server-Sent Events stream — live agent_events feed.

    Frontend usage:
        const es = new EventSource('/api/events/stream', {headers: {Authorization: 'Bearer ...'}});
        es.onmessage = e => { const ev = JSON.parse(e.data); ... };
    """
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx/Caddy proxy buffering disable
            "Connection": "keep-alive",
        },
    )


@router.post("/events/publish")
async def publish_event(body: dict, _user=Depends(require_admin)):
    """Manual event publish (testing/admin use). body = {member, action, detail}"""
    await publish_to_redis(body)
    return {"ok": True}


async def publish_to_redis(event: dict) -> None:
    """team.log_event se call hota hai — non-blocking, fail-open.
    Redis channel 'lgai:events' pe JSON publish karta hai."""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        payload = json.dumps(event, ensure_ascii=False, default=str)
        await r.publish(_CHANNEL, payload)
        await r.aclose()
    except Exception:
        pass  # fail-open — caller never breaks
