"""requirements.lock.txt must pin pydantic and pydantic-core as a COMPATIBLE pair.

Issue #237. The lock pinned `pydantic==2.13.4` with `pydantic_core==2.47.0`, but
pydantic 2.13.4's own metadata declares `pydantic-core==2.46.4`. Installing the
lock with `--no-deps` (what Dockerfile.lock and both CI workflows do) therefore
produced an unimportable app:

    SystemError: The installed pydantic-core version (2.47.0) is incompatible
    with the current pydantic version, which requires 2.46.4.

That took the `tests` workflow permanently red on main from `d451b56c` onward --
it died at `app.main` import, so every step after it was skipped and the workflow
produced zero signal for weeks.

Why it hid for so long: three consumers of the same lock behaved differently.
  * Dockerfile.lock  -- correct BY ACCIDENT. Later `pip install` passes that run
    WITH deps (torch, silero-vad, pipecat, kokoro) re-resolve and quietly
    downgrade pydantic-core back to 2.46.4. Production runs the right pair, but
    nothing guarantees it.
  * ci.yml           -- correct BY EXPLICIT GUARD (a
    `--force-reinstall pydantic-core==2.46.4` step added after this bit someone).
  * tests.yml        -- had neither, so it got the lock's literal (broken) pin.

Fixing the lock makes all three deterministic and retires the need for the guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

LOCK = Path(__file__).resolve().parents[1] / "requirements.lock.txt"

# `pydantic-core` and `pydantic_core` are the same distribution; the lock has
# historically used both spellings, so normalise before comparing.
_PIN = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*==\s*([^\s;#]+)", re.MULTILINE)


def _normalise(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _lock_pins() -> dict[str, str]:
    return {_normalise(m.group(1)): m.group(2) for m in _PIN.finditer(LOCK.read_text("utf-8"))}


def test_lockfile_exists():
    assert LOCK.is_file(), f"requirements.lock.txt missing at {LOCK}"


def test_pydantic_and_core_both_pinned():
    pins = _lock_pins()
    assert "pydantic" in pins, "pydantic must stay pinned in the lock"
    assert "pydantic-core" in pins, "pydantic-core must stay explicitly pinned in the lock"


def test_lock_pins_the_core_version_pydantic_actually_requires():
    """The regression guard for #237.

    Reads the requirement straight from the installed pydantic's metadata rather
    than hardcoding 2.46.4, so a future pydantic bump only needs the lock updated
    -- this test keeps verifying the pair rather than a frozen literal.
    """
    import importlib.metadata as md

    pins = _lock_pins()

    try:
        requires = md.requires("pydantic") or []
    except md.PackageNotFoundError:  # pragma: no cover - pydantic is a hard dep
        pytest.skip("pydantic not installed in this environment")

    required = [
        r for r in requires if _normalise(r.split("==")[0].split(";")[0]) == "pydantic-core"
    ]
    if not required:  # pragma: no cover - defensive
        pytest.skip("installed pydantic does not pin pydantic-core exactly")

    expected = required[0].split("==", 1)[1].split(";")[0].strip()

    assert pins["pydantic-core"] == expected, (
        f"lock pins pydantic-core=={pins['pydantic-core']} but the pinned "
        f"pydantic=={pins.get('pydantic')} requires pydantic-core=={expected}. "
        "Installing the lock with --no-deps would make `import app.main` raise "
        "SystemError (issue #237)."
    )
