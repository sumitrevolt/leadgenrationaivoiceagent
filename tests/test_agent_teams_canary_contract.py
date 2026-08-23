"""Agent Teams canary contract — doc must exist; fail-not-skip when missing (F4)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "canary_frozen.py"
CANARY_DOC = REPO / "docs" / "coordination" / "AGENT_TEAMS_CANARY.md"
SSOT_REL = "docs/coordination/canary_frozen_paths.yml"
RENDER_MARKER = "canary_frozen_paths.yml"


def _load():
    spec = importlib.util.spec_from_file_location("canary_frozen", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_agent_teams_canary_doc_coupled_to_ssot():
    """Missing canary doc = hard FAIL (never skip). Present doc must mirror SSOT."""
    mod = _load()
    paths = mod.frozen_paths()
    prefix = mod.branch_prefix()
    assert mod.max_teammates() == 2

    if not CANARY_DOC.is_file():
        pytest.fail(
            f"missing Agent Teams canary doc: {CANARY_DOC.relative_to(REPO)} "
            "(TM1 must merge AGENT_TEAMS_CANARY.md before this contract can pass; "
            "fail-not-skip per F4)"
        )

    text = CANARY_DOC.read_text(encoding="utf-8")

    # Frozen paths: either each SSOT entry appears, or doc points at SSOT + render marker
    if SSOT_REL in text and RENDER_MARKER in text:
        pass
    else:
        for p in paths:
            assert p in text, f"canary doc missing frozen path from SSOT: {p}"

    assert prefix in text or "agent/tm" in text, f"canary doc must mention branch_prefix={prefix!r}"
    assert "2" in text or "2 teammates" in text.lower() or ("TM1" in text and "TM2" in text), (
        "canary doc must mention max teammates (2) or merge_order TM1/TM2"
    )
