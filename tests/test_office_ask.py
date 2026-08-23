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
        "kind": "task",
        "member": "manager",
        "scope": "team",
    }
    assert hq._ask_heuristic_route("kitne hot leads hain?")["kind"] == "question"


def test_ask_context_from_snapshot_compact():
    ctx = hq._ask_context_from_snapshot(
        {
            "metrics": {"leads_today": 4, "calls": 2},
            "approvals": {"counts": {"sales": 3}},
            "next_best_actions": [{"title": "Hot queue clear karo"}],
            "system_health": {"dlq": 0},
            "agents": [{"key": "isha", "name": "Isha", "status": "working"}],
        }
    )
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
    assert body["ok"] is True
    assert body["kind"] == "question"
    assert body["text"] == "sab set"


def test_api_ask_task_shape_for_command_bar(monkeypatch):
    async def fake_ask(q):
        return {
            "ok": True,
            "kind": "task",
            "member": "isha",
            "scope": "solo",
            "run_id": "run_1",
            "text": "Isha ne kaam draft kar diya",
        }

    monkeypatch.setattr(hq, "hq_ask", fake_ask)
    r = _client().post("/api/platform/office/ask", json={"q": "post banao"})
    assert r.status_code == 200
    body = r.json()
    for key in ("ok", "kind", "text", "member", "scope", "run_id"):
        assert key in body
    assert body["kind"] == "task"
    assert body["text"]


def test_api_ask_validates_empty():
    r = _client().post("/api/platform/office/ask", json={"q": ""})
    assert r.status_code == 422  # pydantic min_length


# --------------------------------------------------------------------------- #
# Broadcast — "sabhi agents ko command" (2026-07-03 user-ask)
# --------------------------------------------------------------------------- #
def test_heuristic_route_broadcast():
    assert (
        hq._ask_heuristic_route("sabhi agents ko bolo apna status report do")["kind"] == "broadcast"
    )
    assert hq._ask_heuristic_route("puri team lag jao diwali campaign pe")["kind"] == "broadcast"


async def test_hq_ask_broadcast_fans_out_to_runnables(monkeypatch):
    async def fake_route(q):
        return {"kind": "broadcast", "member": "", "scope": "team"}

    seen = {}

    async def fake_fan_out(goal, agents=None, max_agents=4):
        seen.update(goal=goal, agents=list(agents or []), max_agents=max_agents)
        return {
            "ok": True,
            "goal": goal,
            "agents": agents,
            "results": [
                {"agent": "isha", "output": "post idea ready"},
                {"agent": "rohan", "output": "outreach list bana"},
            ],
            "summary": "sab lag gaye kaam pe",
            "at": "2026-07-03T12:00:00",
        }

    monkeypatch.setattr(hq, "_ask_route", fake_route)
    import app.agents.coordinator as coordinator

    monkeypatch.setattr(coordinator, "fan_out", fake_fan_out)
    res = await hq.hq_ask("sabhi agents ko bolo aaj revenue pe focus karo")
    assert res["ok"] is True and res["kind"] == "broadcast"
    assert set(seen["agents"]) == set(hq.RUNNABLE_MEMBERS)  # doer-set, capped
    assert "Isha" in res["text"] and "Rohan" in res["text"]
    assert "sab lag gaye" in res["text"]


def test_boss_brief_headline_has_aaj_label_and_hot():
    """Sync-perception fix: window-label 'Aaj' + hot count same headline me."""
    brief = hq.build_boss_brief(
        {
            "metrics": {"new_leads_today": 0, "qualified_leads_today": 0, "mrr": 0},
            "pipeline": [{"id": "scoring_qualification", "count": 11}],
            "approvals": {"counts": {"total_pending": 21}},
            "system_health": {},
        }
    )
    assert brief["headline"].startswith("Aaj:")
    assert "11 hot ready" in brief["headline"]
    assert "21 approval" in brief["recommendation"]["label"]


def test_ask_context_total_pending_first():
    ctx = hq._ask_context_from_snapshot(
        {
            "approvals": {"counts": {"coordinator": 14, "sales": 7, "total_pending": 21}},
        }
    )
    assert "TOTAL pending=21" in ctx
    assert ctx.index("TOTAL pending=21") < ctx.index("coordinator=14")
