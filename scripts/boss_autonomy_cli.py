"""Compatibility shim — forwards to scripts/boss_autonomy.py CLI.

The canonical thin CLI is scripts/boss_autonomy.py. This entrypoint exists so
older invocations of scripts/boss_autonomy_cli.py keep working unchanged.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent / "boss_autonomy.py"
_spec = importlib.util.spec_from_file_location("_boss_autonomy_cli_impl", _SCRIPT)
_impl = importlib.util.module_from_spec(_spec)
sys.modules["_boss_autonomy_cli_impl"] = _impl
_spec.loader.exec_module(_impl)


def amain() -> int:
    return int(_impl.amain() or 0)


if __name__ == "__main__":
    sys.exit(amain())
