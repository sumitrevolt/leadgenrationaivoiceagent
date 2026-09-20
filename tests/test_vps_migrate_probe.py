"""Guard: `vps_migrate.sh` must probe an alembic INVOCATION, never an import.

Root cause of the 2026-09-19 partial deploy. The script resolved alembic with

    elif python3 -c "import alembic" >/dev/null 2>&1; then ALEMBIC="python3 -m alembic"

From `/opt/leadgen` the repo's own `alembic/` migrations directory lands on
`sys.path` ahead of site-packages and satisfies `import alembic` as a PEP-420
namespace package (`alembic.__path__` was `_NamespacePath(['/opt/leadgen/alembic'])`).
So the probe reported success on a host with no working alembic, the script
printed "using: python3 -m alembic", and `upgrade head` died on
"No module named alembic" -- inside `deploy_vps.sh`, which runs the migration
gate *after* it has already moved the checkout. A misleading FATAL, and a
half-applied release.

The containers DO have it (`/opt/venv/bin/alembic`, re-verified 2026-09-20), so
the fix is to prefer a running container and to test any host candidate by
running it. These tests are text assertions on the script; the anti-vacuity test
proves they fail against the shape that shipped.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "vps_migrate.sh"
TEXT = SCRIPT.read_text(encoding="utf-8")

# The exact mistake: gating a candidate on a bare import probe.
IMPORT_PROBE = re.compile(r"""python3?\s+-c\s+["']import\s+alembic""")


def _code(text: str) -> str:
    """Strip whole-line comments: the header documents the old dangerous probe
    on purpose, and a comment that quotes a bug is not an invocation of it."""
    return "\n".join(
        ln for ln in text.splitlines() if not ln.strip().startswith("#")
    )


CODE = _code(TEXT)


def test_script_exists_and_is_valid_bash():
    assert SCRIPT.is_file()
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    r = subprocess.run(
        [bash, "-n", str(SCRIPT)], capture_output=True, text=True, cwd=str(REPO)
    )
    assert r.returncode == 0, r.stderr


def test_no_candidate_is_gated_on_a_bare_import_probe():
    assert not IMPORT_PROBE.search(CODE), (
        "`python3 -c \"import alembic\"` succeeds from /opt/leadgen even when no "
        "alembic is installed, because the repo's own alembic/ migrations "
        "directory shadows the package. Probe the invocation instead."
    )


def test_host_module_candidate_probes_the_module_invocation():
    """`python3 -m alembic --help` is the smallest check that actually works."""
    assert re.search(r"python3?\s+-m\s+alembic\s+--help", CODE), (
        "the host module candidate must be gated on running `python3 -m alembic`, "
        "not on importing it"
    )


def test_running_container_is_the_first_candidate():
    """The image ships /opt/venv/bin/alembic; the prod host venv does not exist."""
    lines = CODE.splitlines()
    ifs = [i for i, ln in enumerate(lines) if re.match(r"^if .*docker ps", ln)]
    assert ifs, "expected a `docker ps` guard as the leading branch"
    body = "\n".join(lines[ifs[0] : ifs[0] + 3])
    assert "docker exec" in body and "alembic" in body, body


def test_script_still_fails_closed_when_nothing_works():
    assert re.search(r"\bexit\s+1\b", CODE), "must refuse loudly, not carry on"
    assert "FATAL" in CODE, (
        "the no-alembic path must name the cause; a bare traceback is what made "
        "the 2026-09-19 failure diagnosable only after the fact"
    )


# --------------------------------------------------------------------------- #
# anti-vacuity: these assertions must reject the shape that actually shipped
# --------------------------------------------------------------------------- #

BROKEN = """#!/usr/bin/env bash
set -euo pipefail
cd /opt/leadgen
if [ -x .venv/bin/alembic ]; then
  ALEMBIC=".venv/bin/alembic"
elif python3 -c "import alembic" >/dev/null 2>&1; then
  ALEMBIC="python3 -m alembic"
else
  echo "FATAL: no alembic available"
  exit 1
fi
$ALEMBIC upgrade head
"""


def test_detector_rejects_the_regression():
    assert IMPORT_PROBE.search(BROKEN), (
        "the import-probe detector is vacuous -- it must match the 2026-09-19 line"
    )
    assert not re.search(r"python3?\s+-m\s+alembic\s+--help", BROKEN)
    assert not re.match(r"^if .*docker ps", BROKEN, re.M)
