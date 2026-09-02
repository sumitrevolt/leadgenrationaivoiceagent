"""Static assertions on frontend/delivery_command_center.html — the new
'Automation Runs' admin panel (Task 6: automation-log visibility) that surfaces
the ADR-064 DB-backed /api/admin/automation-logs endpoint (was API-only, no UI).

Mirrors tests/test_customer_dashboard_frontend.py:
 (1) node --check syntax gate on inline <script>,
 (2) no-removal guard: existing cockpit wiring must still be present,
 (3) per-feature markers for the new panel + its real backend fetch.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).resolve().parents[1] / "frontend" / "delivery_command_center.html"
SRC = HTML_PATH.read_text(encoding="utf-8")

# Existing cockpit wiring that must NOT be removed by this change.
PRE_EXISTING = [
    'id="logsBody"',
    'id="customerTableWrap"',
    "/api/admin/delivery-cockpit",
    "/api/admin/delivery-logs",
    "function loadLogs",
    "function loadAll",
]

# New Automation Runs panel markers.
NEW_MARKERS = [
    'id="autoRunsBody"',
    "/api/admin/automation-logs",
    "function renderAutoRuns",
    "async function loadAutoRuns",
    "run-filter",
    'id="runApply"',
]


def _inline_js() -> str:
    blocks = re.findall(r"<script>(.*?)</script>", SRC, re.S)
    assert blocks, "no inline <script> block found"
    return "\n;\n".join(blocks)


def test_inline_js_syntax_ok(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not on PATH")
    f = tmp_path / "dcc_inline.js"
    f.write_text(_inline_js(), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_existing_cockpit_wiring_present():
    missing = [m for m in PRE_EXISTING if m not in SRC]
    assert not missing, f"cockpit wiring vanished: {missing}"


def test_automation_runs_panel_present():
    missing = [m for m in NEW_MARKERS if m not in SRC]
    assert not missing, f"automation-runs markers missing: {missing}"


def test_automation_runs_loaded_in_loadall():
    # loadAutoRuns must be invoked by the initial cockpit load.
    assert "loadAutoRuns();" in SRC
