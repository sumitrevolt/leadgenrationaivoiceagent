"""Regression lock for the outbound `call_completed` webhook wiring.

BUG (fixed): app/telephony/call_manager.py fired the post-call "call_completed"
event via ``outbound_webhooks.fire_event(...)``. There is no ``fire_event`` on
that module — only the async ``emit()`` — so the call raised AttributeError and
was silently swallowed by the enclosing ``try/except: pass``. The event NEVER
fired for any completed call.

These tests lock the correct public API (``emit``) and assert no telephony module
re-introduces a dead ``outbound_webhooks.fire_event(...)`` call.

Pure-python: a light module import + source scans. NO network, NO DB.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TELE = ROOT / "app" / "telephony"
CALLMGR = TELE / "call_manager.py"


def _src(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def test_outbound_webhooks_api_is_emit_not_fire_event():
    """The module exposes the async emit(); fire_event() must not exist."""
    from app.platform import outbound_webhooks as ow

    assert callable(getattr(ow, "emit", None)), "outbound_webhooks.emit() must exist"
    assert not hasattr(ow, "fire_event"), (
        "outbound_webhooks has no fire_event() — callers must use emit()"
    )


def test_no_telephony_module_calls_outbound_fire_event():
    """Regression lock: a `<alias>.fire_event(` call against outbound_webhooks is
    dead code (AttributeError swallowed by try/except). None may exist."""
    offenders: list[str] = []
    for p in sorted(TELE.glob("*.py")):
        src = _src(p)
        if "fire_event" not in src:
            continue
        for m in re.finditer(r"(\w+)\.fire_event\s*\(", src):
            alias = m.group(1)
            bound = re.search(rf"import outbound_webhooks as {alias}\b", src)
            if bound or alias == "outbound_webhooks":
                ln = src[: m.start()].count("\n") + 1
                offenders.append(f"{p.name}:{ln}")
    assert not offenders, f"dead outbound_webhooks.fire_event() call(s): {offenders}"


def test_call_manager_fires_call_completed_via_emit():
    """Positive lock: call_manager wires the call_completed event through emit()."""
    src = _src(CALLMGR)
    assert re.search(r"\.emit\(\s*[\"']call_completed[\"']", src), (
        "call_manager must fire 'call_completed' via outbound_webhooks.emit()"
    )
