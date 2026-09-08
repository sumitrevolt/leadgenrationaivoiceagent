"""Read-only Failed Jobs / DLQ panel in the delivery cockpit.

Surfaces the EXISTING GET /api/growth/infra/dlq (key=failed/dead) — no new
route, no backend change. Mirrors tests/test_automation_runs_panel.py.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).resolve().parents[1] / "frontend" / "delivery_command_center.html"
SRC = HTML_PATH.read_text(encoding="utf-8")

PRE_EXISTING = [
    'id="autoRunsBody"',
    "/api/admin/automation-logs",
    "function loadAll",
]

NEW_MARKERS = [
    'id="dlqBody"',
    "/api/growth/infra/dlq",
    "function renderDlq",
    "async function loadDlq",
    "dlq-filter",
]


def _inline_js() -> str:
    blocks = re.findall(r"<script>(.*?)</script>", SRC, re.S)
    assert blocks, "no inline <script> block found"
    return "\n;\n".join(blocks)


def test_inline_js_syntax_ok(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not on PATH")
    f = tmp_path / "dcc_dlq.js"
    f.write_text(_inline_js(), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_existing_wiring_present():
    missing = [m for m in PRE_EXISTING if m not in SRC]
    assert not missing, f"cockpit wiring vanished: {missing}"


def test_dlq_panel_present():
    missing = [m for m in NEW_MARKERS if m not in SRC]
    assert not missing, f"dlq panel markers missing: {missing}"


def test_dlq_loaded_in_loadall():
    assert "loadDlq();" in SRC
