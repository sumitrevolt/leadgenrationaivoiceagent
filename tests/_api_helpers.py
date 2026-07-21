"""Shared assertions for the canonical API error envelope and mounted routes."""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any


def _stringify(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True)
    return str(value or "")


def api_error_message(response_or_body: Any) -> str:
    """Return the canonical error message, with legacy-detail compatibility."""
    body = response_or_body.json() if hasattr(response_or_body, "json") else response_or_body
    if not isinstance(body, dict):
        return ""

    error = body.get("error")
    if isinstance(error, dict) and "message" in error:
        return _stringify(error["message"])
    return _stringify(body.get("detail"))


def iter_mounted_routes(app_or_router: Any) -> Iterator[Any]:
    """Yield leaf routes with paths, including routes nested in router wrappers."""
    seen: set[int] = set()

    def _walk(node: Any, prefix: str = "") -> Iterator[Any]:
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)

        original_router = getattr(node, "original_router", None)
        if original_router is not None:
            context = getattr(node, "include_context", None)
            include_prefix = getattr(context, "prefix", "")
            yield from _walk(original_router, prefix + include_prefix)
            return

        children = getattr(node, "routes", None)
        if children is not None:
            for child in children:
                yield from _walk(child, prefix)
            return

        path = getattr(node, "path", None)
        if path is not None:
            yield SimpleNamespace(path=f"{prefix}{path}", original_route=node)

    yield from _walk(app_or_router)
