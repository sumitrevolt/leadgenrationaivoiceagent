"""Contract tests for the 1000-Engineers skill (DSH skill + repo wrappers).

Locks the always-loaded collective-engineering knowledge:
- canonical DSH skill file exists with required structure (frontmatter, §0, D1-D12, §2)
- DSH system-prompt (cordis.yml) injects the doctrine and points to the canonical file
- repo skill wrapper exists and is registered in CLAUDE.md/AGENTS.md startup protocol
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_SKILL = ROOT / "deploy" / "dsh" / "skills" / "1000-engineers.md"
CORDIS = ROOT / "deploy" / "dsh" / "cordis.yml"
WRAPPER_SKILL = ROOT / ".claude" / "skills" / "thousand-engineers" / "SKILL.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
AGENTS_MD = ROOT / "AGENTS.md"


@pytest.fixture(scope="module")
def canonical() -> str:
    return CANONICAL_SKILL.read_text(encoding="utf-8")


def test_canonical_skill_exists_with_frontmatter(canonical: str) -> None:
    assert canonical.startswith("---"), "canonical skill must have YAML frontmatter"
    assert "name: dsh-1000-engineers" in canonical
    assert "description:" in canonical


def test_canonical_skill_has_required_sections(canonical: str) -> None:
    for section in ["§0 Universal Invariants", "§1 The 10-Lens Review"]:
        assert section in canonical, f"missing {section}"
    for i in range(1, 13):
        assert f"### D{i}." in canonical, f"missing discipline pack D{i}"
    assert "§2 The Pre-Ship Gate" in canonical


def test_canonical_skill_is_substantive(canonical: str) -> None:
    assert len(canonical.splitlines()) >= 200, "1000-engineers skill too thin"
    assert "Evidence over vibes" in canonical


def test_dsh_system_prompt_injects_doctrine() -> None:
    cordis = CORDIS.read_text(encoding="utf-8")
    assert "1000-Engineers Collective Knowledge" in cordis
    assert "deploy/dsh/skills/1000-engineers.md" in cordis
    assert "fail-CLOSED" in cordis


def test_repo_wrapper_skill_exists() -> None:
    wrapper = WRAPPER_SKILL.read_text(encoding="utf-8")
    assert wrapper.startswith("---")
    assert "name: thousand-engineers" in wrapper
    assert "deploy/dsh/skills/1000-engineers.md" in wrapper


def test_startup_protocol_references_skill() -> None:
    claude = CLAUDE_MD.read_text(encoding="utf-8")
    agents = AGENTS_MD.read_text(encoding="utf-8")
    assert "thousand-engineers" in claude
    assert "thousand-engineers" in agents
    assert claude == agents, "AGENTS.md must stay a byte-copy of CLAUDE.md"


def test_no_secrets_in_skill_files() -> None:
    import re

    for path in (CANONICAL_SKILL, WRAPPER_SKILL, CORDIS):
        text = path.read_text(encoding="utf-8")
        for marker in ("sk-", "api_key=", "AIza", "ghp_"):
            assert marker not in text, f"possible secret marker {marker!r} in {path.name}"
        assert not re.search(r"\bBearer\s+[A-Za-z0-9]", text), (
            f"literal bearer token in {path.name}"
        )
        assert not re.search(r"\b[0-9a-f]{40,}\b", text), f"long hex literal in {path.name}"
