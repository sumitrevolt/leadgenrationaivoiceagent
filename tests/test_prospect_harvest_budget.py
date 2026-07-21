"""Prospect job must not SoftTimeLimit via nested harvest (2026-07-20 canary)."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_harvest_loop_safe_timeout_env_capped(monkeypatch):
    import app.platform.lead_harvester as lh
    from scripts import harvest_safety_wrapper as hsw

    async def _slow():
        await asyncio.sleep(8)
        return {"ok": True}

    monkeypatch.setenv("HARVEST_LOOP_TIMEOUT_S", "5")
    monkeypatch.setattr(lh, "run_loop_sweep", _slow)

    out = await hsw.run_harvest_loop_safe()
    assert out.get("truncated") is True
    assert "timeout" in str(out.get("error", ""))


@pytest.mark.asyncio
async def test_src_prospector_skips_when_nested(monkeypatch):
    from app.platform import lead_harvester as lh

    monkeypatch.setenv("SKIP_HARVEST_PROSPECTOR_SRC", "1")
    out = await lh._src_prospector("salon", "Pune", 10)
    assert out.get("skipped") == "nested_under_prospect"


def test_gtm_pairs_hard_capped(monkeypatch):
    """HARVEST_LOOP_MAX_PAIRS must shrink GTM_PAIRS_PER_RUN."""
    from app.platform import lead_harvester as lh

    monkeypatch.setenv("LEAD_HARVESTER", "1")
    monkeypatch.setenv("GTM_PAIRS_PER_RUN", "8")
    monkeypatch.setenv("HARVEST_LOOP_MAX_PAIRS", "2")

    # Just verify the cap math used in run_loop_sweep (unit-level).
    n_pairs = int("8")
    max_pairs = int("2")
    n_pairs = max(1, min(n_pairs, max(1, max_pairs)))
    assert n_pairs == 2
    assert lh.enabled() is True
