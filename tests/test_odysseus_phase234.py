"""Tests — Odysseus Phase 2-4: Model Cookbook + Deep Research + Docs AI-Edit.

All routers are INERT-default (503 without their env flag). Tests monkeypatch
the flag and stub out external calls (free_ai.chat, searxng.search).
"""

from __future__ import annotations

import asyncio
import importlib

import pytest


# ================================================================
# Phase 2 · Model Cookbook
# ================================================================


def _mc(monkeypatch, enabled=True):
    monkeypatch.setenv("MODEL_COOKBOOK_ENABLED", "1" if enabled else "0")
    import app.api.model_cookbook as m

    importlib.reload(m)
    return m


def test_mc_inert_default(monkeypatch):
    m = _mc(monkeypatch, enabled=False)
    with pytest.raises(Exception) as exc:
        m._require_enabled()
    assert getattr(exc.value, "status_code", None) == 503


def test_mc_catalog_shape(monkeypatch):
    m = _mc(monkeypatch)
    for row in m._CATALOG:
        for key in ("provider", "model", "speed", "quality", "multilingual", "cost", "best_for"):
            assert key in row, f"missing {key} in {row['provider']}"
        assert row["speed"] in ("fast", "medium", "slow")
        assert row["quality"] in ("excellent", "good", "fair")


def test_mc_recommend_for_salon(monkeypatch):
    m = _mc(monkeypatch)
    # force all providers "configured"
    monkeypatch.setattr(
        m.free_ai, "_provider_flags", lambda: {r["provider"]: True for r in m._CATALOG}
    )

    async def _run():
        out = await m.recommend(m.RecommendIn(niche="salon"), _user=object())
        assert out["niche"] == "salon"
        assert out["top_pick"] in [r["provider"] for r in m._CATALOG]
        # salon tasks include voice_reply / hinglish → mistral or gemini should be near top
        assert out["recommended_full_chain"], "chain empty"
        assert set(out["matched_tasks"]) & {"voice_reply", "hinglish"}

    asyncio.run(_run())


def test_mc_recommend_explicit_task(monkeypatch):
    m = _mc(monkeypatch)
    monkeypatch.setattr(
        m.free_ai, "_provider_flags", lambda: {r["provider"]: True for r in m._CATALOG}
    )

    async def _run():
        out = await m.recommend(m.RecommendIn(niche="ignored", task="content_gen"), _user=object())
        assert out["matched_tasks"] == ["content_gen"]
        # cerebras / sambanova should appear (content_gen recipe)
        assert set(out["recommended_full_chain"]) & {"cerebras", "sambanova"}

    asyncio.run(_run())


def test_mc_recommend_no_live_falls_back_to_full(monkeypatch):
    m = _mc(monkeypatch)
    monkeypatch.setattr(m.free_ai, "_provider_flags", lambda: {})

    async def _run():
        out = await m.recommend(m.RecommendIn(niche="salon"), _user=object())
        # live empty → falls back to full chain
        assert out["recommended_live_chain"] == out["recommended_full_chain"]

    asyncio.run(_run())


# ================================================================
# Phase 3 · Deep Research
# ================================================================


def _dr(monkeypatch, enabled=True):
    monkeypatch.setenv("DEEP_RESEARCH_ENABLED", "1" if enabled else "0")
    import app.api.deep_research as m

    importlib.reload(m)
    return m


def test_dr_inert_default(monkeypatch):
    m = _dr(monkeypatch, enabled=False)
    with pytest.raises(Exception) as exc:
        m._require_enabled()
    assert getattr(exc.value, "status_code", None) == 503


def test_dr_run_requires_searxng(monkeypatch):
    m = _dr(monkeypatch)
    monkeypatch.setattr(m.searxng, "enabled", lambda: False)

    async def _run():
        with pytest.raises(Exception) as exc:
            await m.run(m.ResearchIn(topic="test topic"), _user=object())
        assert getattr(exc.value, "status_code", None) == 503

    asyncio.run(_run())


def test_dr_full_flow_mocked(monkeypatch):
    m = _dr(monkeypatch)
    monkeypatch.setattr(m.searxng, "enabled", lambda: True)

    async def fake_chat(*, system, messages, **kwargs):
        # planner returns 3 lines, synthesizer returns report
        if "planner" in system.lower() or "query" in system.lower():
            return "query about A\nquery about B\nquery about C", "test"
        return "# Report\nSome body [1][2].\n\nBottom line: works.", "test"

    async def fake_search(q, count=6, **kw):
        return [
            {"title": f"Result for {q} #1", "url": f"https://ex.com/{q}/1", "content": "snip 1"},
            {"title": f"Result for {q} #2", "url": f"https://ex.com/{q}/2", "content": "snip 2"},
        ]

    monkeypatch.setattr(m.free_ai, "chat", fake_chat)
    monkeypatch.setattr(m.searxng, "search", fake_search)

    async def _run():
        out = await m.run(m.ResearchIn(topic="best CRMs for salons"), _user=object())
        assert out["queries"], "no queries planned"
        assert len(out["queries"]) >= 1
        assert out["sources"], "no sources"
        assert (
            out["report_markdown"].startswith("# Report") or "Bottom line" in out["report_markdown"]
        )
        assert out["elapsed_ms"] >= 0

    asyncio.run(_run())


def test_dr_planner_fallback_on_empty_llm(monkeypatch):
    m = _dr(monkeypatch)

    async def empty_chat(**kwargs):
        return "", "test"

    monkeypatch.setattr(m.free_ai, "chat", empty_chat)

    async def _run():
        qs = await m._plan_queries("fallback topic", 4)
        # empty LLM → topic-only fallback
        assert qs == ["fallback topic"]

    asyncio.run(_run())


def test_dr_dedupe_sources():
    import app.api.deep_research as m

    groups = [
        [{"url": "https://a.com/1", "title": "A"}, {"url": "https://b.com/1", "title": "B"}],
        [{"url": "https://a.com/1", "title": "A dup"}, {"url": "https://c.com/1", "title": "C"}],
    ]
    out = m._dedupe_sources(groups, top_k=5)
    urls = [s["url"] for s in out]
    assert urls == ["https://a.com/1", "https://b.com/1", "https://c.com/1"]


# ================================================================
# Phase 4 · Docs AI-Edit
# ================================================================


def _dx(monkeypatch, enabled=True):
    monkeypatch.setenv("DOCS_AI_EDIT_ENABLED", "1" if enabled else "0")
    import app.api.docs_ai_edit as m

    importlib.reload(m)
    return m


def test_dx_inert_default(monkeypatch):
    m = _dx(monkeypatch, enabled=False)
    with pytest.raises(Exception) as exc:
        m._require_enabled()
    assert getattr(exc.value, "status_code", None) == 503


def test_dx_unknown_action_rejected(monkeypatch):
    m = _dx(monkeypatch)

    async def _run():
        with pytest.raises(Exception) as exc:
            await m.run_edit(m.EditIn(text="Hello", action="explode"), _user=object())
        assert getattr(exc.value, "status_code", None) == 400

    asyncio.run(_run())


def test_dx_improve_action(monkeypatch):
    m = _dx(monkeypatch)

    async def fake_chat(*, system, messages, **kwargs):
        # basic sanity — system prompt should mention 'rewrite' or 'clarity' for improve
        assert "rewrite" in system.lower() or "clarity" in system.lower()
        return "Improved: " + messages[-1]["content"], "test-provider"

    monkeypatch.setattr(m.free_ai, "chat", fake_chat)

    async def _run():
        out = await m.run_edit(m.EditIn(text="Salon opens 10am.", action="improve"), _user=object())
        assert out["action"] == "improve"
        assert out["edited_text"].startswith("Improved: ")
        assert out["provider"] == "test-provider"
        assert out["input_chars"] == len("Salon opens 10am.")
        assert out["output_chars"] > 0

    asyncio.run(_run())


def test_dx_change_tone_uses_tone_in_system(monkeypatch):
    m = _dx(monkeypatch)
    seen = {}

    async def fake_chat(*, system, messages, **kwargs):
        seen["system"] = system
        return "Toned text", "test"

    monkeypatch.setattr(m.free_ai, "chat", fake_chat)

    async def _run():
        out = await m.run_edit(
            m.EditIn(text="hi there", action="change_tone", tone="hinglish"),
            _user=object(),
        )
        assert out["tone"] == "hinglish"
        assert "hinglish" in seen["system"].lower()

    asyncio.run(_run())


def test_dx_empty_llm_returns_502(monkeypatch):
    m = _dx(monkeypatch)

    async def empty_chat(**kwargs):
        return "", "test"

    monkeypatch.setattr(m.free_ai, "chat", empty_chat)

    async def _run():
        with pytest.raises(Exception) as exc:
            await m.run_edit(m.EditIn(text="hi", action="improve"), _user=object())
        assert getattr(exc.value, "status_code", None) == 502

    asyncio.run(_run())


def test_dx_actions_list(monkeypatch):
    m = _dx(monkeypatch)

    async def _run():
        out = await m.list_actions(_user=object())
        assert "improve" in out["actions"]
        assert "change_tone" in out["actions"]
        assert "hinglish" in out["tones"]

    asyncio.run(_run())


# ================================================================
# Registry + router membership
# ================================================================


def test_all_flags_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS

    for f in (
        "LLM_COMPARE_ENABLED",
        "MODEL_COOKBOOK_ENABLED",
        "DEEP_RESEARCH_ENABLED",
        "DOCS_AI_EDIT_ENABLED",
    ):
        assert f in AUTOMATION_FLAGS, f"{f} missing from AUTOMATION_FLAGS"


def test_routers_expose_expected_paths():
    import app.api.model_cookbook as mc
    import app.api.deep_research as dr
    import app.api.docs_ai_edit as dx

    for m, expected in [
        (mc, ["/api/cookbook/models", "/api/cookbook/recommend", "/api/cookbook/ui"]),
        (dr, ["/api/research/deep/run", "/api/research/deep/status", "/api/research/deep/ui"]),
        (dx, ["/api/docs/edit/run", "/api/docs/edit/actions", "/api/docs/edit/ui"]),
    ]:
        paths = {getattr(r, "path", "") for r in m.router.routes}
        for p in expected:
            assert p in paths, f"{p} missing in {m.__name__}"
