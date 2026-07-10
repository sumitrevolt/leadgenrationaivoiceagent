"""Version-compatible inspection of FastAPI's effective registered routes."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def iter_effective_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Yield direct and lazily included routes with effective prefixes.

    FastAPI 0.139 keeps ``include_router`` branches lazy and exposes their
    resolved paths through the public ``iter_route_contexts`` helper. Older
    FastAPI versions use eager route lists and do not provide that helper.
    """
    route_list = list(routes)
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # FastAPI eager-router versions
        yield from route_list
        return
    for route_context in iter_route_contexts(route_list):
        if getattr(route_context, "path", ""):
            yield route_context
            continue
        # FastAPI 0.139 RouteContext leaves ``path`` empty for lazily included
        # WebSocket routes, while its resolved Starlette route carries the full
        # prefix. Normalize that compatibility edge for audits/startup checks.
        effective = getattr(route_context, "_effective_route", None)
        starlette_route = getattr(effective, "starlette_route", None)
        yield starlette_route or route_context


__all__ = ["iter_effective_routes"]
