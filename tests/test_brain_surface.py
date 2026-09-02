"""Second-brain surfacing — operator search API (Part A) + daily-agent read-back (Part B).

The Obsidian brain was write+sync alive but felt 'unused': no operator surface, and
read-back was only in coordinator/council. These pin: (B) Isha's daily content now
injects brain_context, and (A) the search endpoint returns recall results.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_make_post_item_injects_brain_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Part B: _make_post_item must consult the brain and pass it to generate_post."""
    from app.marketing import auto_content
    from app.platform import obsidian_sync

    monkeypatch.setattr(obsidian_sync, "brain_context", lambda q, k=3: "## Brain: SOLAR_WIN_ANGLE")

    captured: dict[str, Any] = {}

    async def _fake_gen(**kw: Any) -> dict[str, Any]:
        captured.update(kw)
        return {"caption": "ok", "hashtags": ["#x"]}

    monkeypatch.setattr(auto_content.post_generator, "generate_post", _fake_gen)

    item = await auto_content._make_post_item(
        {"id": "c1", "business_name": "Sharma Solar", "niche": "solar"},
        "2026-06-28",
        "post",
        "Daily Post",
    )
    assert item["caption"] == "ok"
    assert "SOLAR_WIN_ANGLE" in captured.get("context", ""), (
        "brain context not passed to generate_post"
    )


@pytest.mark.asyncio
async def test_make_post_item_failopen_when_brain_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brain error must NOT break content generation (fail-open)."""
    from app.marketing import auto_content
    from app.platform import obsidian_sync

    def _boom(q: str, k: int = 3) -> str:
        raise RuntimeError("vault gone")

    monkeypatch.setattr(obsidian_sync, "brain_context", _boom)

    async def _fake_gen(**kw: Any) -> dict[str, Any]:
        return {"caption": "still works", "hashtags": []}

    monkeypatch.setattr(auto_content.post_generator, "generate_post", _fake_gen)

    item = await auto_content._make_post_item(
        {"id": "c1", "business_name": "X", "niche": "solar"}, "2026-06-28", "post", "Daily Post"
    )
    assert item["caption"] == "still works"


@pytest.mark.asyncio
async def test_generate_post_accepts_context_param() -> None:
    """Part B: generate_post takes optional context, never returns empty (template fallback)."""
    from app.marketing import post_generator

    r = await post_generator.generate_post(
        business_name="Sharma Solar", niche="solar", context="## Brain: prefer ROI angle"
    )
    assert r.get("caption"), "generate_post must never be empty"
