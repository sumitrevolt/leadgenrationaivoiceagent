"""niche_prospector must not blow Celery soft-limit after scrape (2026-07-20 DLQ)."""

from __future__ import annotations

import asyncio
import time as time_mod

import pytest


@pytest.mark.asyncio
async def test_niche_run_bounds_post_scrape_rescore(monkeypatch, tmp_path):
    from app.platform import niche_prospector as np

    monkeypatch.setattr(np, "_CURSOR", str(tmp_path / "cursor.json"))
    monkeypatch.setattr(
        np, "_all_niche_keys", lambda tier=None, leadgen_only=True: ["salon", "dental"]
    )
    monkeypatch.setattr(
        np,
        "build_targets",
        lambda **kw: [{"niche": "salon", "query": "salon", "cities": ["Pune"]}],
    )

    async def _fake_prospecting(_limit=6):
        return {"ok": True, "by_niche": {"salon": 2}, "queries_run": 1}

    calls: list[int] = []

    async def _fake_rescore(limit=500):
        calls.append(limit)
        await asyncio.sleep(0.01)
        return {"ok": True, "scored": limit}

    import app.platform.lead_scoring as lead_scoring
    import app.platform.prospector as prospector

    monkeypatch.setattr(prospector, "run_prospecting", _fake_prospecting)
    monkeypatch.setattr(lead_scoring, "rescore_db", _fake_rescore)

    out = await np.run(batch=4, advance=False)
    assert out["ok"] is True
    assert calls == [100]  # was unbounded 2000
    assert "rescore" in out


@pytest.mark.asyncio
async def test_niche_run_skips_rescore_when_scrape_already_long(monkeypatch, tmp_path):
    from app.platform import niche_prospector as np

    monkeypatch.setattr(np, "_CURSOR", str(tmp_path / "cursor.json"))
    monkeypatch.setattr(np, "_all_niche_keys", lambda tier=None, leadgen_only=True: ["salon"])
    monkeypatch.setattr(
        np,
        "build_targets",
        lambda **kw: [{"niche": "salon", "query": "salon", "cities": ["Pune"]}],
    )

    # t0=0; after scrape elapsed check sees 500s → skip rescore.
    # monkeypatch patches the GLOBAL time.monotonic, so ANYTHING running during
    # this test (async teardown, an active log handler, etc.) also consumes it.
    # A bare finite iterator raised StopIteration on the 5th call, which PEP 479
    # turns into "RuntimeError: generator raised StopIteration" at teardown.
    # Serve the intended sequence to the code under test, then HOLD the last value
    # so surplus calls are harmless. Exhaustion is the intended terminal protocol
    # here (clock stops advancing), handled semantically — not a blind suppression.
    _seq = iter([0.0, 500.0, 501.0, 502.0])
    _clock = {"t": 502.0}

    def _fake_monotonic():
        try:
            _clock["t"] = next(_seq)
        except StopIteration:
            pass
        return _clock["t"]

    monkeypatch.setattr(time_mod, "monotonic", _fake_monotonic)

    async def _fake_prospecting(_limit=6):
        return {"ok": True, "by_niche": {"salon": 1}}

    called = {"n": 0}

    async def _fake_rescore(limit=500):
        called["n"] += 1
        return {"ok": True}

    import app.platform.lead_scoring as lead_scoring
    import app.platform.prospector as prospector

    monkeypatch.setattr(prospector, "run_prospecting", _fake_prospecting)
    monkeypatch.setattr(lead_scoring, "rescore_db", _fake_rescore)

    out = await np.run(batch=2, advance=False)
    assert out["ok"] is True
    assert called["n"] == 0
    assert out.get("rescore", {}).get("skipped") is True
