"""Process-local async runner for synchronous Celery tasks."""

from __future__ import annotations

import asyncio
import threading

_LOOP: asyncio.AbstractEventLoop | None = None
_LOCK = threading.Lock()


def run(coro):
    global _LOOP
    with _LOCK:
        if _LOOP is None or _LOOP.is_closed():
            _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
        loop = _LOOP
    return loop.run_until_complete(coro)


def reset_for_tests() -> None:
    global _LOOP
    with _LOCK:
        loop = _LOOP
        _LOOP = None
    if loop is None or loop.is_closed():
        return
    try:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
