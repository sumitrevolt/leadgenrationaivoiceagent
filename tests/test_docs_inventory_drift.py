"""Docs must not hardcode stale inventory counts — source of truth is code."""

from __future__ import annotations

import re
from pathlib import Path

from app.platform import blueprint_graph as bg
from app.platform.scheduler_config import JOB_META

REPO = Path(__file__).resolve().parent.parent


def test_agent_registry_does_not_hardcode_stale_24_jobs():
    text = (REPO / "docs" / "AGENT_REGISTRY.md").read_text(encoding="utf-8")
    assert "24 jobs" not in text.lower()
    assert "JOB_META" in text


def test_job_meta_count_is_positive_and_matches_len():
    assert len(JOB_META) >= 40
    # Sanity: heading in AGENT_REGISTRY should not claim a different fixed integer.
    text = (REPO / "docs" / "AGENT_REGISTRY.md").read_text(encoding="utf-8")
    for m in re.finditer(r"parity\s*\((\d+)\s*jobs?\)", text, flags=re.I):
        assert int(m.group(1)) == len(JOB_META)


def test_architecture_blueprint_banner_defers_to_validate_graph():
    text = (REPO / "docs" / "ARCHITECTURE_BLUEPRINT.md").read_text(encoding="utf-8")
    assert "validate_graph" in text or "blueprint_graph" in text
    r = bg.validate_graph(strict_files=False)
    assert r["ok"]
    counts = r["counts"]
    assert counts["nodes"] == 59
    assert counts["edges"] == 56
    assert counts["flows"] == 11
    assert counts["orphans"] == 0
    assert counts["workforce"] == 31


def test_truth_matrix_points_at_idempotency_production_proof():
    text = (REPO / "docs" / "agent_runtime" / "TRUTH_MATRIX.md").read_text(encoding="utf-8")
    assert "DISTRIBUTED_IDEMPOTENCY_PRODUCTION_PROOF.md" in text


def test_readiness_matrix_banner_is_superseded_not_authority():
    text = (REPO / "docs" / "context" / "AUTOMATION_MAX_READINESS_MATRIX.md").read_text(
        encoding="utf-8"
    )
    assert "SUPERSEDED" in text
    assert "328" in text or "327" in text
    assert "59" in text
    # Must not still claim dial HARD-OFF as current policy authority
    assert "PLATFORM_DIAL_DAILY=0` + `data/platform_dial.json enabled:false`" not in text
