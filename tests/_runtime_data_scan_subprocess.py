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

import hashlib
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

# ── Shared on-disk cache (2026-09-19) ────────────────────────────────────────
# Three modules request the SAME repo-wide scan, and the per-module
# ``scope="module"`` fixtures do not dedupe across them. Under ``pytest -n auto``
# each of the N xdist workers then ran its own 2-6 heavy ~135s AST subprocesses
# concurrently on the 2-core CI runner; all 10 workers died with "node down: Not
# properly terminated" and the required ``prod_check + pytest`` context went red
# on PR #531. The scan is a pure function of the repo tree, so the result is
# cached in the pytest basetemp (shared by every xdist worker) and the expensive
# walk happens once per session instead of once per worker per module.
# Deleting the cache file (or setting RD_SCAN_NO_CACHE=1) forces a fresh scan.
_CACHE_ENV_DISABLE = "RD_SCAN_NO_CACHE"


def _cache_dir() -> Path | None:
    """A directory every xdist worker can see, or None to skip caching.

    ``PYTEST_DEBUG_TEMPROOT`` is set for the whole session and inherited by
    workers, so it is the one location all of them agree on. Falls back to the
    system temp root when pytest is not driving (direct script use).
    """
    base = os.environ.get("PYTEST_DEBUG_TEMPROOT") or tempfile.gettempdir()
    try:
        d = Path(base) / "rd_scan_cache"
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        return None


def _cache_key(repo: Path) -> str:
    """Stable key over repo identity + the files the scan result depends on.

    Includes the mtime/size of the scanner, the allowlist, and the manifest so a
    code change invalidates the cache instead of silently asserting against a
    stale graph. CI is a clean checkout, so the key is effectively constant
    there — exactly the savings we want, with no staleness risk.
    """
    parts: list[str] = [str(repo)]
    for rel in (
        "app/platform/runtime_data_scan.py",
        "app/platform/runtime_data_allowlist.py",
        "app/platform/runtime_data_allowlist_entries.py",
        "app/platform/runtime_data_manifest.py",
        "app/platform/runtime_data_baseline.py",
        "app/platform/runtime_data_baseline_changes.py",
    ):
        p = repo / rel
        try:
            st = p.stat()
            parts.append(f"{rel}:{int(st.st_mtime)}:{st.st_size}")
        except OSError:
            parts.append(f"{rel}:missing")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"findings-{digest}.json"


def scan_repo_in_subprocess(repo: Path) -> list[dict[str, Any]]:
    """Return ``scan.scan_repo`` findings via a one-shot child interpreter."""
    repo = Path(repo).resolve()
    try:
        timeout_s = float(os.environ.get("RD_SCAN_TIMEOUT_S", _DEFAULT_SCAN_TIMEOUT_S))
    except (TypeError, ValueError):
        timeout_s = _DEFAULT_SCAN_TIMEOUT_S

    cache_file: Path | None = None
    if not os.environ.get(_CACHE_ENV_DISABLE):
        cdir = _cache_dir()
        if cdir is not None:
            cache_file = cdir / _cache_key(repo)
            try:
                cached = cache_file.read_text(encoding="utf-8")
            except OSError:
                cached = ""
            if cached:
                # A truncated/partial file from a concurrent writer is treated as
                # a miss and rescanned, never as an authoritative empty result.
                try:
                    return json.loads(cached)
                except json.JSONDecodeError:
                    pass

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
        payload = out.read_text(encoding="utf-8")
        if cache_file is not None:
            # Atomic publish: a reader never observes a half-written file.
            try:
                tmp = cache_file.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, cache_file)
            except OSError:
                pass  # caching is an optimisation; a write failure is not fatal
        return json.loads(payload)
