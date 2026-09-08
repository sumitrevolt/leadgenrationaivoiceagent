"""P0: a denied preflight must stop `vps_force_pull.py` before it mutates anything.

Ordering tests read text. This suite goes further and proves *behaviour*: with a
failing preflight substituted, the destructive command chain is never executed.

Why this script specifically: its chain begins with `git stash`, which removes
the live-mutated files under `data/` from the working tree — the invoice ledger,
consent ledger, suppression ledgers and customer registry all live there today.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TARGET = SCRIPTS / "vps_force_pull.py"


def _load():
    spec = importlib.util.spec_from_file_location("vps_force_pull_under_test", TARGET)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


def test_denied_preflight_prevents_all_mutation(mod, monkeypatch) -> None:
    """THE test: preflight fails -> no subprocess chain, non-zero exit."""
    monkeypatch.setattr(mod, "preflight_ok", lambda: False)

    executed: list[str] = []

    def _spy(*args, **kwargs):  # pragma: no cover - must never run
        executed.append(str(args))
        raise AssertionError("destructive command executed after a DENIED preflight")

    monkeypatch.setattr(mod.subprocess, "run", _spy)

    rc = mod.main()

    assert rc != 0, "a denied deployment must not exit 0"
    assert rc == 90
    assert executed == [], "no command may run after denial"


def test_denial_is_not_swallowed(mod, monkeypatch) -> None:
    """A try/except around the guard would make denial indistinguishable from approval."""
    source = TARGET.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in source.splitlines() if not ln.strip().startswith("#"))
    assert "except" not in code.split("def main")[1], (
        "main() must not catch exceptions around the guard"
    )
    assert "|| true" not in code
    assert "--force" not in code


def _executable_source(path: Path) -> str:
    """Code only — module docstring and comments stripped.

    The prose deliberately says "there is no bypass flag"; a naive substring
    scan flagged that sentence as a bypass. Documentation describing a
    prohibition is not an implementation of it.
    """
    text = path.read_text(encoding="utf-8")
    # Drop the leading module docstring.
    if text.lstrip().startswith('"""'):
        start = text.index('"""')
        end = text.index('"""', start + 3) + 3
        text = text[end:]
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#")).upper()


def test_no_bypass_env_var(mod) -> None:
    code = _executable_source(TARGET)
    for token in ("BYPASS", "SKIP_PREFLIGHT", "FORCE_DEPLOY", "IGNORE_GUARD"):
        assert token not in code, f"bypass affordance found in code: {token}"


def test_preflight_runs_check_deploy_mode(mod) -> None:
    source = TARGET.read_text(encoding="utf-8")
    assert "check-deploy" in source
    assert "runtime_data_preflight.py" in str(mod.PREFLIGHT)


def test_allowed_preflight_permits_the_chain(mod, monkeypatch) -> None:
    """Anti-regression: the guard must not brick a legitimate deployment."""
    monkeypatch.setattr(mod, "preflight_ok", lambda: True)
    seen: dict[str, object] = {}

    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_run(cmd, *a, **k):
        seen["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    rc = mod.main()
    assert rc == 0
    assert "git stash" in str(seen["cmd"])
    assert "git pull origin main" in str(seen["cmd"])


def test_preflight_ok_propagates_nonzero(mod, monkeypatch) -> None:
    """`preflight_ok()` must report False on any non-zero exit."""

    class _Denied:
        returncode = 1
        stdout = ""
        stderr = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Denied())
    assert mod.preflight_ok() is False


def test_preflight_ok_true_only_on_zero(mod, monkeypatch) -> None:
    class _Ok:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Ok())
    assert mod.preflight_ok() is True
