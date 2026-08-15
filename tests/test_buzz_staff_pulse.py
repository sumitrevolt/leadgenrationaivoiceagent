"""Staff pulse must not trip Buzz mention-preflight."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "buzz_staff_pulse", REPO / "scripts" / "buzz_staff_pulse.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["buzz_staff_pulse"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_pulse_imports_without_localappdata(monkeypatch):
    """Linux CI has no LOCALAPPDATA; collection must not KeyError."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    pulse = _load()
    assert callable(pulse.build_message)


def test_pulse_footer_does_not_at_mention_boss():
    """Hourly task was rc=3 because CLI mention-preflight treated @Boss as a ping."""
    pulse = _load()
    body = pulse.build_message(
        {
            "totals": {
                "actions_today": 0,
                "errors_today": 0,
                "working_members": 0,
                "active_members": 0,
            },
            "members": [],
        }
    )
    assert "@" not in body
