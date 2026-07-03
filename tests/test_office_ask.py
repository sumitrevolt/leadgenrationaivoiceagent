"""Tests for HQ Ask (office_hq.hq_ask + POST /api/platform/office/ask).

Risk surface = intent routing (task vs question), draft-safe dispatch reuse
(run_agent_task), grounded-answer fallback (LLM fail -> snapshot facts), and
the never-raise contract. LLM/coordinator sab monkeypatched — koi network nahi.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.platform.office_hq as hq


def _client() -> TestClient:
    from app.api import auth_deps
    from app.main import app

    app.dependency_overrides[auth_deps.require_admin] = lambda: type("U", (), {"email": "t@t"})()
    return TestClient(app)


def test_heuristic_route_task_vs_question():
    assert hq._ask_heuristic_route("naya blog likho aaj") == {
        "kind": "task", "member": "manager", "scope": "team"}
    assert hq._ask_heuristic_route("kitne hot leads hain?")["kind"] == "question"


def test_ask_context_from_snapshot_compact():
    ctx = hq._ask_context_from_snapshot({
        "metrics": {"leads_today": 4, "calls": 2},
        "approvals": {"counts": {"sales": 3}},
        "next_best_actions": [{"title": "Hot queue clear karo"}],
        "system_health": {"dlq": 0},
        "agents": [{"key": "isha", "name": "Isha", "status": "working"}],
    })
    assert "leads_today=4" in ctx
    assert "sales=3" in ctx
    assert "Hot queue" in ctx
    assert "Staff active: 1/1" in ctx
    assert len(ctx) <= 1400
    assert hq._ask_context_from_snapshot({}) == ""


async def test_hq_ask_empty_message():
    res = await hq.hq_ask("   ")
    assert res["ok"] is False


async def test_hq_ask_question_grounded_answer(monkeypatch):
    async def fake_route(q):
        return {"kind": "question", "member": "", "scope": ""}

    async def fake_snapshot():
        return {"metrics": {"leads_today": 7}}

    async def fake_chat(system, messages, **kw):
        assert "leads_today=7" in system  # grounded facts prompt me hone chahiye
        return "Aaj 7 naye leads aaye — sab theek chal raha.", "mistral"

    monkeypatch.setattr(hq, "_ask_route", fake_route)
    monkeypatch.setattr(hq, "build_snapshot", fake_snapshot)
    import app.voice_agent.free_ai as free_ai

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    res = await hq.hq_ask("aaj kitne leads aaye?")
    assert res["ok"] is True and res["kind"] == "question"
    assert "7 naye leads" in res["text"]


async def test_hq_ask_question_llm_fail_degrades_to_facts(monkeypatch):
    async def fake_route(q):
        return {"kind": "question", "member": "", "scope": ""}

    async def fake_snapshot():
        return {"metrics": {"leads_today": 7}}

    async def boom_chat(*a, **kw):
        raise RuntimeError("all providers down")

    monkeypatch.setattr(hq, "_ask_route", fake_route)
    monkeypatch.setattr(hq, "build_snapshot", fake_snapshot)
    import app.voice_agent.free_ai as free_ai

    monkeypatch.setattr(free_ai, "chat", boom_chat)
    res = await hq.hq_ask("status?")
    assert res["ok"] is True
    assert "leads_today=7" in res["text"]  # honest degrade — facts, no fabrication


async def test_hq_ask_task_dispatches_via_kaam_do(monkeypatch):
    async def fake_route(q):
        return {"kind": "task", "member": "isha", "scope": "solo"}

    calls = {}

    async def fake_run(member, goal, scope):
        calls.update(member=member, goal=goal, scope=scope)
        return {"ok": True, "status": "done", "summary": "post draft ban gaya", "run_id": "r1"}

    monkeypatch.setattr(hq, "_ask_route", fake_route)
    monkeypatch.setattr(hq, "run_agent_task", fake_run)
    res = await hq.hq_ask("diwali ka social post banao")
    assert res["ok"] is True and res["kind"] == "task" and res["member"] == "isha"
    assert calls["goal"] == "diwali ka social post banao"
    assert "post draft ban gaya" in res["text"]
    assert res["run_id"] == "r1"


async def test_ask_route_llm_bad_json_falls_back(monkeypatch):
    async def bad_chat(*a, **kw):
        return "hmm pata nahi", "mistral"

    import app.voice_agent.free_ai as free_ai

    monkeypatch.setattr(free_ai, "chat", bad_chat)
    res = await hq._ask_route("prospects dhundo jaipur me")
    assert res["kind"] == "task"  # heuristic fallback (dhundo)
    assert res["member"] == "manager"


def test_api_ask_endpoint(monkeypatch):
    async def fake_ask(q):
        return {"ok": True, "kind": "question", "text": "sab set"}

    monkeypatch.setattr(hq, "hq_ask", fake_ask)
    r = _client().post("/api/platform/office/ask", json={"q": "sab theek?"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["text"] == "sab set"


def test_api_ask_validates_empty():
    r = _client().post("/api/platform/office/ask", json={"q": ""})
    assert r.status_code == 422  # pydantic min_length
