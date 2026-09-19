"""Regression tests for the admin user-create verification email (finding B-8).

POSTMORTEM — 2026-09-18
-----------------------
`app/api/admin.py` sent the "your account was created" email with:

    from app.platform.auto_outreach import EmailSender as _ES
    _es = _ES()
    _es.send(to=..., subject=..., body=...)

Three independent defects, all invisible because everything sat inside a
best-effort `try/except` that logged at DEBUG:

1. `app.platform.auto_outreach` **never exported** `EmailSender` — it imports
   the class lazily *inside* its own functions. The import raised ImportError.
2. `EmailSender` lives in `app.integrations.email_sender`.
3. Even with the right import, the API is `await send_email(to_emails=[...])`,
   not `send(to=...)`.

Net effect: an admin-created user silently never received their verification
email. These tests are source-based (no route/auth/db plumbing) and generalise
the guard: **every** `from app.X import Y` inside a `try` block in admin.py must
resolve to a real attribute, because that is precisely where failures hide.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADMIN_PY = ROOT / "app" / "api" / "admin.py"


def _best_effort_app_imports() -> list[tuple[str, str]]:
    """(module, name) for every `from app... import name` inside a try block."""
    tree = ast.parse(ADMIN_PY.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.ImportFrom) and (stmt.module or "").startswith("app."):
                for alias in stmt.names:
                    if alias.name != "*":
                        found.append((stmt.module, alias.name))
    return found


def _resolves(module: str, name: str) -> bool:
    """Attribute semantics of `from module import name` (submodule-aware)."""
    mod = importlib.import_module(module)
    try:
        getattr(mod, name)
        return True
    except AttributeError:
        pass
    try:  # `from app.platform import admin_2fa` imports a submodule
        importlib.import_module(f"{module}.{name}")
        return True
    except ImportError:
        return False


def test_the_guard_actually_finds_imports() -> None:
    """A guard that scans nothing is a false-safety test."""
    imports = _best_effort_app_imports()
    assert imports, "best-effort import scan found nothing — the AST walk broke"
    assert any(m == "app.integrations.email_sender" for m, _ in imports)


@pytest.mark.parametrize("module,name", _best_effort_app_imports())
def test_best_effort_app_imports_resolve(module: str, name: str) -> None:
    assert _resolves(module, name), (
        f"{ADMIN_PY.name} does `from {module} import {name}` inside a try block, "
        f"but that name does not exist — the failure will be swallowed silently. "
        f"Point the import at the module that actually defines it."
    )


def test_auto_outreach_still_does_not_export_email_sender() -> None:
    """Documents the trap that caused the outage — and fails if it silently returns."""
    from app.platform import auto_outreach

    assert not hasattr(auto_outreach, "EmailSender")


def test_email_sender_api_contract() -> None:
    """The canonical sender is async and takes a list of recipients."""
    from app.integrations.email_sender import EmailSender

    assert inspect.iscoroutinefunction(EmailSender.send_email)
    params = list(inspect.signature(EmailSender.send_email).parameters)
    assert params[1] == "to_emails", params
    assert not hasattr(EmailSender, "send"), (
        "EmailSender.send() does not exist — a call to it always raised AttributeError"
    )


def test_verification_email_uses_canonical_sender_and_api() -> None:
    src = ADMIN_PY.read_text(encoding="utf-8")
    assert "from app.integrations.email_sender import EmailSender" in src
    assert "await _es.send_email(" in src
    assert "to_emails=[user.email]" in src


def test_verification_email_failure_is_not_logged_at_debug() -> None:
    """DEBUG is how this bug stayed invisible; keep it at WARNING or above."""
    src = ADMIN_PY.read_text(encoding="utf-8")
    assert "verification email failed" in src
    for line in src.splitlines():
        if "verification email" in line and "logger.debug" in line:
            pytest.fail(f"verification-email failure logged at DEBUG: {line.strip()}")
