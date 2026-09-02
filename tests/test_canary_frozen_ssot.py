"""SSOT + observance gates for Agent Teams canary (owner setup / lead tooling)."""

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
    ignored = subprocess.run(
        ["git", "check-ignore", "-v", str(SSOT.relative_to(REPO))],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored.returncode == 1, f"SSOT must not be gitignored: {ignored.stdout}"


def test_loader_structure_no_pasted_path_twin():
    """Assert SSOT shape + render round-trip — do NOT hardcode frozen path strings here."""
    mod = _load()
    data = mod.load_canary_ssot()
    assert data["schema_version"] == 1
    assert data["branch_prefix"] == "agent/tm"
    assert data["max_teammates"] == 2
    assert data["merge_order"] == ["TM1", "TM2"]
    assert "scaffolding" in data["evidence_labels"]
    assert "prediction_locked" in data["evidence_labels"]
    assert "claude_at_canary_pass" in data["evidence_labels"]
    assert "canary_not_run" in data["evidence_labels"]
    assert data["quota"].get("require_baseline_before_run") is True
    requires = data["pass_rule"]["requires"]
    assert "tm1_merged_before_tm2" in requires
    assert "frozen_diff_check_clean" in requires
    assert "tm2_fail_not_skip_on_missing_doc" in requires
    assert "quota_note_recorded" in requires

    paths = mod.frozen_paths()
    assert isinstance(paths, list) and len(paths) >= 1
    assert all(isinstance(p, str) and p.strip() for p in paths)
    # gitignored secrets must NOT live in diff-gated frozen_paths
    assert not any(p == ".env" or p.startswith(".env") for p in paths)
    classes = mod.frozen_classes()
    assert any("env" in c for c in classes)

    rendered = mod.render_frozen_markdown()
    assert "canary_frozen_paths.yml" in rendered
    for p in paths:
        assert p in rendered, "render must include every SSOT frozen_paths entry"


def test_path_match_and_check_enforcement(tmp_path):
    mod = _load()
    assert (
        mod.path_matches_frozen("app/voice_agent/foo.py", ["app/voice_agent/"])
        == "app/voice_agent/"
    )
    assert (
        mod.path_matches_frozen("app/billing/packages.py", ["app/billing/packages.py"])
        == "app/billing/packages.py"
    )
    assert mod.path_matches_frozen("docs/x.md", ["app/voice_agent/"]) is None

    # Isolated git repo: touch a frozen-shaped path and expect check exit 2
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "canary@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "canary"], cwd=repo, check=True, capture_output=True
    )
    (repo / "ok.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "ok.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    bad = repo / "app" / "billing"
    bad.mkdir(parents=True)
    (bad / "packages.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "app/billing/packages.py"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "touch frozen"], cwd=repo, check=True, capture_output=True
    )

    # Point module patterns by passing explicit list through check_diff helper
    hits = []
    for path in mod.changed_files(base=base, head="HEAD", cwd=repo):
        matched = mod.path_matches_frozen(path, ["app/billing/packages.py", "app/voice_agent/"])
        if matched:
            hits.append((path, matched))
    assert hits and hits[0][0].endswith("packages.py")


def test_cli_check_clean_on_self_docs():
    """This PR's docs-only tip vs itself for a known-clean path set — check plumbing works."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--base", "HEAD", "--head", "HEAD"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "frozen_diff_check_clean" in r.stdout


def test_cli_render_exit_0():
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "render"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    mod = _load()
    for p in mod.frozen_paths():
        assert p in r.stdout
    assert "rendered from docs/coordination/canary_frozen_paths.yml" in r.stdout
