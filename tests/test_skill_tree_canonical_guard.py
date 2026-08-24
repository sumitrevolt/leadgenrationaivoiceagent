"""Phase 12 skill-tree de-duplication guard.

Canonical skill root is `.claude/skills`. The former byte-identical duplicate
tree `.agents/skills` was consolidated in and removed. This guard fails CI if the
duplicate tree reappears, if a consumer bakes/loads the removed root, or if a
skill name is duplicated within the canonical root. It relies only on Git state
(never on a local junction/symlink overlay).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANON = ".claude/skills"
LEGACY = ".agents/skills"


def _tracked(prefix: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", prefix], cwd=ROOT, capture_output=True, text=True
    ).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def test_legacy_duplicate_tree_is_absent() -> None:
    assert _tracked(LEGACY) == [], (
        "The duplicate .agents/skills tree must not exist in Git; "
        "the canonical skill root is .claude/skills."
    )


def test_no_dockerfile_bakes_legacy_root() -> None:
    for df in (
        "Dockerfile.lock",
        "deploy/legacy/Dockerfile",
        "deploy/legacy/Dockerfile.production",
    ):
        p = ROOT / df
        if p.exists():
            assert ".agents/skills" not in p.read_text(encoding="utf-8"), (
                f"{df} still references the removed .agents/skills root"
            )


def test_runtime_code_does_not_reference_legacy_root() -> None:
    out = subprocess.run(
        ["git", "grep", "-l", "--", ".agents/skills", "app"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    offenders = [ln for ln in out.splitlines() if ln.strip()]
    assert offenders == [], f"runtime code references removed .agents/skills: {offenders}"


def test_canonical_root_has_consolidated_skills() -> None:
    dirs = {ln.split("/")[2] for ln in _tracked(CANON) if ln.endswith("/SKILL.md")}
    assert len(dirs) >= 200, f"expected the consolidated skill set under {CANON}, found {len(dirs)}"


def test_no_duplicate_skill_name_within_canonical() -> None:
    dirs = [ln.split("/")[2] for ln in _tracked(CANON) if ln.endswith("/SKILL.md")]
    dupes = sorted({d for d in dirs if dirs.count(d) > 1})
    assert not dupes, f"duplicate canonical skill ids: {dupes}"
