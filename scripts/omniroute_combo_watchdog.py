"""Compatibility entrypoint for the local 14-combo watchdog.

The implementation is kept under docs/openclaw for the OpenClaw runbook; this
stable scripts/ path is used by Task Scheduler and desktop operators.
"""

from __future__ import annotations

from pathlib import Path

_IMPL = Path(__file__).resolve().parents[1] / "docs" / "openclaw" / "scripts" / "omniroute_combo_watchdog.py"
_SOURCE = _IMPL.read_text(encoding="utf-8")
# Execute the shared implementation in this module's namespace so tests and
# operators can patch its probe functions without importing a second module.
_SOURCE = _SOURCE.replace("if __name__ == \"__main__\":\n    sys.exit(main())", "")
exec(compile(_SOURCE, str(_IMPL), "exec"), globals())  # nosecurity
