"""Self-improve harvest must stay bounded and avoid nested prospecting work."""

import asyncio


def test_harvest_action_uses_lightweight_legal_sources(monkeypatch):
    from app.agents import self_improve
    from app.platform import lead_harvester

    captured = {}

    async def fake_run_harvest(*args, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "new_leads": 2,
            "deduped": 1,
            "enrich": {"found": 0},
        }

    monkeypatch.setattr(lead_harvester, "run_harvest", fake_run_harvest)

    result = asyncio.run(self_improve._execute("harvest_leads", "bounded harvest"))

    assert result["ok"] is True
    assert captured["limit"] == 4
    assert captured["sources"] == ["osm", "websearch", "opendata"]
    assert "prospector" not in captured["sources"]
