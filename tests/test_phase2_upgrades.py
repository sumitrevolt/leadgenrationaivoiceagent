"""Unit tests for Phase-2 upgrades (semantic router, greeting audio cache, prospector->DB).

Free-stack only. Self-contained: explicit event loops (no pytest-asyncio dependency).
"""

import asyncio
import inspect

from app.agents import supervisor
from app.voice_agent import latency as L


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---- Task 3: semantic router (keyword fallback) ---------------------------------
def test_keyword_router_still_works():
    assert supervisor.route_for_task("research the kb profile") == "data_agent"
    assert supervisor.route_for_task("start a calling campaign") == "leads_agent"
    assert supervisor.route_for_task("") == "leads_agent"


def test_semantic_router_falls_back_to_keyword(monkeypatch):
    # langgraph absent -> zero-latency keyword route (no LLM call).
    monkeypatch.setattr(supervisor, "AGENTS_AVAILABLE", False, raising=False)
    assert _run(supervisor.semantic_route_for_task("qualify this lead")) == "leads_agent"
    assert _run(supervisor.semantic_route_for_task("enrich kb data")) == "data_agent"
    assert _run(supervisor.semantic_route_for_task("")) == "leads_agent"


def test_supervisor_node_is_async():
    assert inspect.iscoroutinefunction(supervisor.supervisor_node)
    assert inspect.iscoroutinefunction(supervisor.semantic_route_for_task)


# ---- Task 5: pre-synthesized greeting audio cache -------------------------------
def test_audio_cache_roundtrip():
    opt = L.LatencyOptimizer()
    assert opt.get_cached_audio("solar") is None
    opt.cache_audio("solar", b"\x01\x02\x03")
    assert opt.has_cached_audio("solar") is True
    assert opt.get_cached_audio("solar") == b"\x01\x02\x03"
    opt.cache_audio("empty", b"")  # empty bytes ignored
    assert opt.get_cached_audio("empty") is None


def test_presynthesize_greetings_sync_and_async():
    opt = L.LatencyOptimizer()

    class _SyncTTS:
        def synthesize(self, text):
            return ("AUDIO:" + text).encode()

    n = _run(opt.presynthesize_greetings(_SyncTTS(), {"a": "hi", "b": "namaste"}))
    assert n == 2 and opt.get_cached_audio("a") == b"AUDIO:hi"

    class _AsyncTTS:
        async def synthesize(self, text):
            return text.encode()

    opt2 = L.LatencyOptimizer()
    n2 = _run(opt2.presynthesize_greetings(_AsyncTTS(), {"g": "namaste"}))
    assert n2 == 1 and opt2.get_cached_audio("g") == b"namaste"


def test_build_niche_greetings_hinglish():
    g = L.build_niche_greetings(agent_name="Riya")
    assert isinstance(g, dict) and "general" in g
    assert "Riya" in g["general"] and "Namaste" in g["general"]


# ---- Task 2: prospector -> DB persist (safety / never-raise) --------------------
def test_prospector_db_persist_is_safe_on_bad_phone():
    from app.platform import prospector

    assert prospector._persist_prospect_to_db({"phone": ""}) is False
    assert prospector._persist_prospect_to_db({"phone": "123"}) is False  # <10 digits


# ---- Import health / no circular refs ------------------------------------------
def test_imports_no_circular():
    from app.main import app

    assert len(app.routes) > 100
