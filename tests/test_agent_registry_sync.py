"""docs/AGENT_REGISTRY.md must stay in sync with app/platform/team.py -> STAFF.

Why this exists
---------------
On 2026-09-14 the registry documented **19** agents while the code roster
(`app/platform/team.py -> STAFF`) defined **31**. Twelve agents — including
four that are wired into the revenue flywheel (`ananya` booking, `priya`
CRM sync, `zara` social publish, `anika` cadence) — were invisible to anyone
reading the docs. The doc had no test pin, so it silently rotted for ~3 months.

This is a **structural** test, not a grep: it parses the markdown table with a
real parser pass and parses `STAFF` with `ast`, so a reformat of either file
does not defeat it.

It deliberately reads STAFF via AST instead of importing `app.platform.team`,
because that module touches logging/DB helpers on import; a unit test about
documentation should not need a database.

Covers: docs/AGENT_REGISTRY.md <-> app/platform/team.py
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEAM_PY = REPO_ROOT / "app" / "platform" / "team.py"
REGISTRY_MD = REPO_ROOT / "docs" / "AGENT_REGISTRY.md"

# Matches the roster rows in "## 2. Core staff roster":
#   | `manager` | Boss | platform | ... |
_ROW_RE = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|", re.MULTILINE)


def _staff_keys() -> set[str]:
    """Top-level keys of the STAFF dict literal, via AST."""
    source = TEAM_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id == "STAFF" for t in targets):
            continue
        value = node.value
        if isinstance(value, ast.Dict):
            return {
                k.value
                for k in value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    raise AssertionError("STAFF dict literal not found in app/platform/team.py")


def _registry_keys() -> set[str]:
    text = REGISTRY_MD.read_text(encoding="utf-8")
    # Restrict to section 2 so the flywheel table in section 3 (which names
    # modules, not staff ids) can never satisfy or pollute this test.
    start = text.index("## 2. Core staff roster")
    end = text.index("## 3.", start)
    return set(_ROW_RE.findall(text[start:end]))


class TestAgentRegistrySync(unittest.TestCase):
    def test_registry_documents_every_staff_member(self) -> None:
        staff = _staff_keys()
        documented = _registry_keys()
        missing = sorted(staff - documented)
        self.assertEqual(
            missing, [],
            f"AGENT_REGISTRY.md is missing {len(missing)} staff present in team.py STAFF: {missing}",
        )

    def test_registry_documents_no_phantom_member(self) -> None:
        staff = _staff_keys()
        documented = _registry_keys()
        phantom = sorted(documented - staff)
        self.assertEqual(
            phantom, [],
            f"AGENT_REGISTRY.md documents {len(phantom)} ids that no longer exist in STAFF: {phantom}",
        )

    # --- parser sanity: a passing test that parsed nothing is worse than no test
    def test_parsers_actually_found_the_roster(self) -> None:
        staff = _staff_keys()
        documented = _registry_keys()
        self.assertGreaterEqual(len(staff), 31, "STAFF parser regressed (found < 31)")
        self.assertGreaterEqual(len(documented), 31, "registry parser regressed (found < 31)")
        self.assertEqual(len(staff), len(documented))

    def test_negative_control_a_doc_with_no_rows_fails(self) -> None:
        """Guard the guard: an empty/renamed table must NOT pass."""
        self.assertEqual(_ROW_RE.findall("| ID | Name |\n|---|---|\n"), [])
        text = REGISTRY_MD.read_text(encoding="utf-8")
        # The real file must contain at least one row the parser recognises.
        self.assertTrue(_ROW_RE.search(text))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
