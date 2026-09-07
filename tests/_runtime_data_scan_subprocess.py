"""Isolate full-repo ``scan_repo`` walks from the parent pytest process.

CI intermittently SIGSEGVs during cyclic GC (exit 139, ~7% of full-suite
runs, 2026-07-28 measured baseline). The crash is *not* a logic failure of
the scanner — it is a CPython + native-extension interaction that has hit
``scan_repo``, ``markitdown``, and ``team.log_event`` frames interchangeably.

Wrapping the walk in ``gc.freeze()`` cut exposure around the fixture but
did not stop mid-suite crashes elsewhere. Running the walk in a **child
process** keeps the heavy AST graph out of the parent heap entirely, so a
child-side GC fault cannot take down the required pytest job.

Required checks are not weakened: the child must exit 0 and return the
same JSON findings the in-process scanner would emit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_SCAN_SCRIPT = r"""
import json
import sys
from pathlib import Path

from app.platform import runtime_data_allowlist as al
from app.platform import runtime_data_scan as scan

repo = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
findings = scan.scan_repo(repo, allowlist=al.load())
out.write_text(json.dumps(findings), encoding="utf-8")
"""


# A real deadlock must surface as a failure, not an unbounded hang. Measured
# 2026-09-07 on this box: a full-repo scan is ~135s (1329 findings), and
# test_runtime_data_path_allowlist.py runs two of them (~260s total), which is
# why it trips the global pytest ``timeout = 120``. The guard below is
# deliberately far above that so it can only fire on a genuine deadlock.
_DEFAULT_SCAN_TIMEOUT_S = 900.0


def scan_repo_in_subprocess(repo: Path) -> list[dict[str, Any]]:
    """Return ``scan.scan_repo`` findings via a one-shot child interpreter."""
    repo = Path(repo).resolve()
    try:
        timeout_s = float(os.environ.get("RD_SCAN_TIMEOUT_S", _DEFAULT_SCAN_TIMEOUT_S))
    except (TypeError, ValueError):
        timeout_s = _DEFAULT_SCAN_TIMEOUT_S
    with tempfile.TemporaryDirectory(prefix="rd_scan_") as td:
        out = Path(td) / "findings.json"
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _SCAN_SCRIPT, str(repo), str(out)],
                cwd=str(repo),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"scan_repo subprocess exceeded {timeout_s:g}s — this is a "
                "deadlock, not a slow scan (measured full-repo baseline is "
                "~135s). Set RD_SCAN_TIMEOUT_S to override."
            ) from None
        if proc.returncode != 0:
            raise RuntimeError(
                "scan_repo subprocess failed "
                f"(exit {proc.returncode}): {proc.stderr[-2000:] or proc.stdout[-2000:]}"
            )
        return json.loads(out.read_text(encoding="utf-8"))
