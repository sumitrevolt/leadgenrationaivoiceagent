"""SSOT gate for Agent Teams canary frozen paths (owner setup — before live C1)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "canary_frozen.py"
SSOT = REPO / "docs" / "coordination" / "canary_frozen_paths.yml"


def _load():
    spec = importlib.util.spec_from_file_location("canary_frozen", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ssot_file_tracked():
    assert SSOT.is_file()
    # Must not be gitignored (coordination/*.json is ignored; yml must stay tracked)
    ignored = subprocess.run(
        ["git", "check-ignore", "-v", str(SSOT.relative_to(REPO))],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored.returncode == 1, f"SSOT must not be gitignored: {ignored.stdout}"


def test_loader_reads_ssot_not_paste():
    mod = _load()
    data = mod.load_canary_ssot()
    assert data["schema_version"] == 1
    assert data["branch_prefix"] == "agent/tm"
    assert data["max_teammates"] == 2
    paths = mod.frozen_paths()
    assert "app/voice_agent/" in paths
    assert "app/telephony/" in paths
    assert "scripts/deploy_vps.sh" in paths
    assert "app/billing/packages.py" in paths
    assert any(p.startswith(".env") for p in paths)
    assert "pass_rule" in data and "stop_rule" in data
    assert data["quota"].get("measure_after_run") is True


def test_cli_render_exit_0():
    r = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "app/voice_agent/" in r.stdout
    assert "rendered from docs/coordination/canary_frozen_paths.yml" in r.stdout
