"""Contract tests for Agent Teams worktree helper (ADR-172)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "agent_team_worktree.py"


def _load_atw():
    spec = importlib.util.spec_from_file_location("agent_team_worktree", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(args: list[str], *, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        shell=False,
        timeout=60,
        check=False,
    )


def test_settings_enable_agent_teams_flag():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings.get("env", {}).get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") == "1"


def test_adr_and_runbook_present():
    assert (REPO / "docs" / "adr" / "ADR-172-claude-agent-teams-worktrees.md").is_file()
    assert (REPO / "docs" / "adr" / "ADR-173-claw-orchestrator-eval.md").is_file()
    runbook = (REPO / "docs" / "runbooks" / "CLAUDE_AGENT_TEAMS.md").read_text(encoding="utf-8")
    assert "Shared task list ≠ file lock" in runbook or "Shared task list" in runbook
    assert "First-route-wins" in runbook
    assert "canary_frozen_paths.yml" in runbook
    assert "Pass rule" in runbook
    assert "agent/tm" in runbook
    assert (REPO / "docs" / "coordination" / "CANARY_LEAD_PROMPT.md").is_file()
    text = (REPO / "docs" / "adr" / "ADR-173-claw-orchestrator-eval.md").read_text(encoding="utf-8")
    assert "REJECT full install" in text or "REJECT full vendor" in text
    assert "patterns-only" in text.lower() or "FEATURE_HARVEST" in text


def test_invalid_slug_refused():
    r = _run(["create", "--name", "Bad_Slug!"])
    assert r.returncode == 1


def test_outside_root_refused(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    monkeypatch.setenv("AGENT_TEAM_WORKTREE_ROOT", str(root))
    atw = _load_atw()
    outside = tmp_path / "elsewhere" / "agent-team-x"
    with pytest.raises(SystemExit) as ei:
        atw._assert_under_root(outside)
    assert "REFUSED" in str(ei.value)


def test_canary_requires_teammate():
    r = _run(["create", "--canary", "--name", "nope-no-tm"])
    assert r.returncode == 2
    assert "requires --teammate" in (r.stderr + r.stdout)


def test_teammate_branch_naming(tmp_path):
    root = tmp_path / "wt-root"
    root.mkdir()
    env = {**os.environ, "AGENT_TEAM_WORKTREE_ROOT": str(root)}
    slug = "canary-docs"
    create = _run(
        ["create", "--canary", "--name", slug, "--teammate", "1", "--base", "HEAD"],
        env=env,
    )
    assert create.returncode == 0, create.stderr + create.stdout
    assert "agent/tm1/" in create.stdout
    wt = root / f"agent-team-tm1-{slug}"
    assert wt.is_dir()
    head = subprocess.run(
        ["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert head.stdout.strip() == f"agent/tm1/{slug}"
    removed = _run(
        ["remove", "--name", slug, "--teammate", "1", "--force", "--delete-branch"],
        env=env,
    )
    assert removed.returncode == 0, removed.stderr + removed.stdout


def test_create_list_remove_roundtrip(tmp_path):
    root = tmp_path / "wt-root"
    root.mkdir()
    env = {**os.environ, "AGENT_TEAM_WORKTREE_ROOT": str(root)}
    slug = "adr172-smoke"
    create = _run(["create", "--name", slug, "--base", "HEAD"], env=env)
    assert create.returncode == 0, create.stderr + create.stdout
    wt = root / f"agent-team-{slug}"
    assert wt.is_dir()
    assert (wt / ".git").exists() or (wt / ".git").is_file()

    listed = _run(["list"], env=env)
    assert listed.returncode == 0
    assert f"agent-team-{slug}" in listed.stdout

    removed = _run(["remove", "--name", slug, "--force", "--delete-branch"], env=env)
    assert removed.returncode == 0, removed.stderr + removed.stdout
    assert not wt.exists()
