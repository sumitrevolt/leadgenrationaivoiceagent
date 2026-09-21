"""Guard: /api/v1/typesafe/status must not count a consumer it cannot import.

Found while re-verifying U06 candidate 2 on 2026-09-20. The "dynamic consumer
count" rewrite left this block in the status endpoint:

    try:
        from app.integrations.telegram_typesafe import get_telegram_typesafe_router
        active_count += 1
    except Exception:
        pass

`get_telegram_typesafe_router` does not exist anywhere in the repository (the
module exposes `get_intent_classifier`, `get_bot_coordinator`,
`get_response_validator`). The import raised `ImportError` on every request, the
bare `except: pass` swallowed it, and the +1 never fired -- so the endpoint
reported one fewer consumer than it claimed to measure, in code that reads as if
it measures it. An unconditional `+= 1` would have been a different bug (it would
count a consumer that is switched off). Both shapes are the same underlying
mistake: an observability number produced without probing the thing it names.

This is the text-book failure mode already recorded in AGENTS.md §7: a symbol
referenced but not present, invisible until the request path reaches it. These
tests are cheap precisely because the request path DID reach it and said nothing.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROUTES = REPO / "app" / "api" / "typesafe_routes.py"
TEXT = ROUTES.read_text(encoding="utf-8")

# `from a.b.c import Name` — indentation matters: the dead import this guards
# against lived INSIDE the function body, so a `^from` anchored pattern would
# have let it through.
LOCAL_IMPORTS = re.compile(r"^[ \t]*from ((?:app|scripts)\.[\w.]+) import (\w+)", re.M)


def _status_body() -> str:
    start = TEXT.index("async def get_status")
    rest = TEXT[start + len("async def get_status") :]
    end = rest.index("\n@router.")
    return rest[:end]


def test_every_app_relative_import_in_the_file_resolves():
    """A dead `from app...import X` is a runtime ImportError, not a lint."""
    unresolved = []
    for mod, name in LOCAL_IMPORTS.findall(TEXT):
        try:
            module = importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001 - the point of the test
            unresolved.append(f"{mod} failed to import: {exc}")
            continue
        if not hasattr(module, name):
            unresolved.append(f"{mod} has no attribute {name!r}")
    assert not unresolved, (
        "typesafe_routes.py references symbols that do not exist; a function-level "
        "import of a missing name does not fail startup, it only makes the branch "
        "silently never run:\n" + "\n".join(unresolved)
    )


def test_status_does_not_add_an_unconditional_consumer():
    """Every increment must be gated on the consumer's own client state.

    `+= 1` reached for inside a bare `try: import ...` block counts a consumer
    that is switched off, which is the `5 if enabled else 0` bug wearing better
    indentation. The executor's `if get_executor().client.enabled: += 1` is fine
    — the gate is right above it.
    """
    body = _status_body()
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not re.search(r"active_count\s*\+=\s*1\b", line):
            continue
        window = "\n".join(lines[max(0, i - 3) : i])
        assert re.search(r"if\s+.*client\.enabled", window), (
            f"ungated consumer increment at line {i}: {line.strip()!r} — a "
            "consumer counts only if its client is enabled"
        )
    assert "active_count +=" in body


def test_telegram_consumers_are_probed_by_client_state():
    body = _status_body()
    assert "telegram_typesafe" in body, "telegram consumers dropped from the status count"
    probe = re.search(
        r"get_intent_classifier[\s\S]{0,400}?client\.enabled", body
    )
    assert probe, (
        "the telegram block must construct the real accessors and filter on "
        "`.client.enabled` like the bridge consumers do"
    )


def test_telegram_accessors_are_constructible_and_expose_a_client():
    telegram_typesafe = importlib.import_module("app.integrations.telegram_typesafe")
    for accessor in (
        "get_intent_classifier",
        "get_bot_coordinator",
        "get_response_validator",
    ):
        fn = getattr(telegram_typesafe, accessor, None)
        assert callable(fn), f"{accessor}() is gone — update the status probe"
        consumer = fn()
        assert getattr(consumer, "client", None) is not None, (
            f"{accessor}() no longer exposes .client; the status endpoint's "
            "`getattr(s, 'client', None)` filter would silently count 0"
        )
