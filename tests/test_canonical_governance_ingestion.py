#!/usr/bin/env python3
"""Regression tests for canonical governance ingestion (ADR-200 / PR #552).

Verifies that the JSON knowledge store correctly represents both the
lean canonical AGENTS.md (M00-M17 + A01-A10) and the full legacy body
in docs/AGENTS_REFERENCE.md.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _build() -> dict:
    # Import lazily so the test collection does not fail on import error
    from scripts.project_context import build_store
    return build_store()


class TestCanonicalIngestion:
    def test_store_has_both_sources(self) -> None:
        store = _build()
        sources = {n.get("source", "") for n in store["nodes"]}
        # Canonical AGENTS.md must be represented
        assert any("AGENTS.md" in s and "REFERENCE" not in s for s in sources), (
            f"AGENTS.md canonical source missing from store. Got: {sorted(sources)}"
        )
        # Legacy reference must also be represented
        assert any("AGENTS_REFERENCE.md" in s for s in sources), (
            f"AGENTS_REFERENCE.md legacy source missing. Got: {sorted(sources)}"
        )

    def test_canonical_operating_rules_present(self) -> None:
        store = _build()
        ops = [n for n in store["nodes"] if n["type"] == "OperatingRule"]
        assert len(ops) >= 1, "No OperatingRule node ingested from AGENTS.md"
        # Must reference M00-M17 owner directive
        summaries = " ".join(n.get("summary", "") for n in ops)
        assert "M00" in summaries and "MiniMax" in summaries

    def test_canonical_current_state_preferred(self) -> None:
        store = _build()
        states = [n for n in store["nodes"] if n["type"] == "CurrentState"]
        assert len(states) >= 1, "No CurrentState node ingested"
        # Canonical pointer should mention AGENTS_REFERENCE as detail source
        assert any(
            "AGENTS_REFERENCE.md" in n.get("summary", "") for n in states
        ), "Canonical CurrentState should point to AGENTS_REFERENCE.md for detail"

    def test_legacy_landmines_present(self) -> None:
        store = _build()
        landmines = [n for n in store["nodes"] if n["type"] == "Landmine"]
        # Legacy body has many landmines; ensure we ingest them
        assert len(landmines) >= 10, f"Expected ≥10 landmine nodes, got {len(landmines)}"

    def test_legacy_invariants_present(self) -> None:
        store = _build()
        invariants = [n for n in store["nodes"] if n["type"] == "Invariant"]
        assert len(invariants) >= 5, f"Expected ≥5 invariant nodes, got {len(invariants)}"

    def test_project_charter_ingested(self) -> None:
        store = _build()
        projects = [n for n in store["nodes"] if n["type"] == "Project"]
        assert len(projects) >= 1, "No Project node ingested"
        summary = projects[0].get("summary", "")
        assert "FastAPI SaaS" in summary or "leadsgenai.in" in summary

    def test_node_count_matches_expected(self) -> None:
        store = _build()
        # Both canonical + legacy should yield >200 nodes
        assert store["meta"]["node_count"] >= 200, (
            f"Expected ≥200 nodes, got {store['meta']['node_count']}"
        )
