"""Multi-agent COORDINATOR — free-stack, always-on coordination over the STAFF roster.

Existing pieces (REBUILD NAHI): `team.STAFF` (8-staff roster), `staff.py` (concrete
capabilities run_ops/qa/trainer/content/email), `supervisor.py` (langgraph routing,
gated), `staff_supervisor.py` (langgraph-supervisor, heavy/opt-in). GAP = ek
lightweight coordinator jo bina kisi heavy dep ke poore roster ko orchestrate kare.

Coordination mechanisms:
  - supervisor/planner : Boss goal ko ordered sub-tasks me todta (free-LLM).
  - sequential handoff : har agent ka output shared blackboard me → agle agent ko context.
  - parallel fan-out   : independent agents asyncio.gather se ek saath, phir aggregate.
  - shared blackboard  : run-state jo agents read/write karte.
  - traced             : har step `team.log_event` → agent_events (→ /app/team dashboard).

SAFE by default: `execute=False` = sirf reasoning/drafts (zero side-effect). `execute=True`
sirf agent ki SAFE capability fn chalata (woh khud already gated/defensive hain).
Sab free-stack (sirf `free_ai`), no new deps, NEVER raises.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RUNS = os.path.join("data", "coordination_runs.jsonl")
# Allowlisted STAFF keys the coordinator may assign work to.
_AGENTS = ("manager", "rohan", "swara", "dev", "arjun", "meera", "kavya", "isha")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _roster() -> dict[str, dict]:
    try:
        from app.platform.team import STAFF

        return STAFF
    except Exception:
        return {}


def _capabilities() -> dict[str, Callable[[], Awaitable[dict]]]:
    """Agent -> SAFE async capability (existing staff fns; self-gated/defensive)."""
    caps: dict[str, Callable] = {}
    try:
        from app.agents import staff

        caps.update(
            {
                "kavya": staff.run_ops,
                "arjun": staff.run_qa,
                "meera": staff.run_trainer,
                "isha": staff.run_content,
                "rohan": staff.run_email_outreach,
            }
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("coordinator caps err: %s", e)
    return caps


def roster() -> list[dict]:
    """Public roster + which agents have a concrete executable capability."""
    caps = _capabilities()
    return [
        {
            "id": k,
            "name": v.get("name"),
            "title": v.get("title"),
            "duties": v.get("duties"),
            "executable": k in caps,
        }
        for k, v in _roster().items()
    ]


def _log(member: str, action: str, detail: str) -> None:
    try:
        from app.platform.team import log_event

        log_event(member, action, (detail or "")[:180])
    except Exception:
        pass


async def _llm(system: str, user: str, max_tokens: int = 260, temperature: float = 0.4):
    try:
        from app.voice_agent import free_ai

        reply, prov = await free_ai.chat(
            system, [{"role": "user", "content": user}], max_tokens=max_tokens, temperature=temperature
        )
        return (reply or "").strip(), prov
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("coordinator llm err: %s", e)
        return "", "none"


def _extract_list(text: str) -> list:
    t = (text or "").strip()
    i, j = t.find("["), t.rfind("]")
    if i != -1 and j != -1 and j > i:
        t = t[i : j + 1]
    try:
        d = json.loads(t)
        return d if isinstance(d, list) else []
    except Exception:
        return []


async def plan(goal: str, max_steps: int = 5) -> list[dict]:
    """Goal -> ordered [{agent, task}] across allowlisted STAFF. Keyword fallback."""
    roster_desc = "; ".join(f"{k}={v.get('title')}" for k, v in _roster().items())
    sys = (
        "Tum LeadGenAI ke Manager (Boss) ho. Goal ko 2-4 ORDERED sub-tasks me todo, har ek "
        "ek STAFF agent ko assign. SIRF JSON array lautao: "
        '[{"agent":"<key>","task":"<chhota Hinglish task>"}]. '
        f"Allowed keys: {', '.join(_AGENTS)}. Roster: {roster_desc}. Aur kuch mat likho."
    )
    raw, _ = await _llm(sys, f"Goal: {goal}", max_tokens=300, temperature=0.2)
    steps = [
        {"agent": s["agent"], "task": str(s["task"])[:240]}
        for s in _extract_list(raw)
        if isinstance(s, dict) and s.get("agent") in _AGENTS and s.get("task")
    ][:max_steps]
    if steps:
        return steps
    # Fallback: sensible default chain (research -> outreach -> marketing).
    return [
        {"agent": "dev", "task": f"{goal} ke liye research + KB grounding"},
        {"agent": "rohan", "task": f"{goal} ke liye outreach/lead plan"},
        {"agent": "isha", "task": f"{goal} ke liye marketing content"},
    ][:max_steps]


async def _run_agent(agent: str, task: str, blackboard: dict, execute: bool) -> dict:
    """Ek agent apna sub-task kare — concrete capability (execute) ya free-LLM reasoning."""
    caps = _capabilities()
    if execute and agent in caps:
        try:
            res = await caps[agent]()
            return {"mode": "executed", "output": res}
        except Exception as e:  # pragma: no cover - defensive
            return {"mode": "executed", "error": str(e)[:200]}
    v = _roster().get(agent, {})
    prior = json.dumps(blackboard.get("results", [])[-3:], ensure_ascii=False)[:1200]
    sys = (
        f"Tum {v.get('name', agent)} ho — {v.get('title', '')}. Duties: {v.get('duties', '')}. "
        "Apna sub-task concise Hinglish me poora karo (3-5 line, actionable). Sirf output do."
    )
    out, prov = await _llm(
        sys,
        f"Goal: {blackboard.get('goal')}\nTeam ne abhi tak: {prior}\nTumhara task: {task}",
        max_tokens=240,
        temperature=0.5,
    )
    return {"mode": "draft", "output": out or f"({agent} ka draft abhi nahi bana)", "provider": prov}


async def coordinate(goal: str, execute: bool = False, max_steps: int = 5) -> dict:
    """Plan -> sequential handoff over agents (shared blackboard) -> Boss aggregate.

    SAFE default (execute=False = drafts, koi side-effect nahi). Never raises.
    """
    goal = (goal or "").strip()
    if len(goal) < 3:
        return {"ok": False, "error": "goal bahut chhota hai"}
    run_id = uuid.uuid4().hex[:12]
    steps = await plan(goal, max_steps)
    blackboard: dict[str, Any] = {"goal": goal, "results": []}
    _log("manager", "coordinate_start", f"{goal} -> {len(steps)} steps")
    for s in steps:
        agent, task = s["agent"], s["task"]
        res = await _run_agent(agent, task, blackboard, execute)
        blackboard["results"].append({"agent": agent, "task": task, **res})
        _log(agent, "coordinated_step", f"{task} [{res.get('mode')}]")
    summary, _ = await _llm(
        "Tum Manager (Boss) ho. Team ke kaam ko 3-4 line Hinglish summary + ek clear next-action me sameto. Sirf text.",
        f"Goal: {goal}\nTeam results: {json.dumps(blackboard['results'], ensure_ascii=False)[:2000]}",
        max_tokens=220,
        temperature=0.4,
    )
    _log("manager", "coordinate_done", summary or "done")
    out = {
        "ok": True,
        "run_id": run_id,
        "goal": goal,
        "execute": execute,
        "plan": steps,
        "results": blackboard["results"],
        "summary": summary or "(summary abhi nahi bana)",
        "at": _now(),
    }
    _persist(out)
    return out


async def fan_out(goal: str, agents: list[str] | None = None, max_agents: int = 4) -> dict:
    """Parallel coordination — multiple agents ek saath (asyncio.gather), phir aggregate."""
    goal = (goal or "").strip()
    if len(goal) < 3:
        return {"ok": False, "error": "goal bahut chhota hai"}
    ags = [a for a in (agents or ["dev", "rohan", "isha", "kavya"]) if a in _AGENTS][:max_agents]
    bb = {"goal": goal, "results": []}

    async def one(a: str):
        return a, await _run_agent(a, f"{goal} (apne role se)", bb, False)

    pairs = await asyncio.gather(*[one(a) for a in ags], return_exceptions=True)
    results = []
    for p in pairs:
        if isinstance(p, tuple):
            a, r = p
            results.append({"agent": a, **r})
            _log(a, "fanout_step", goal)
    summary, _ = await _llm(
        "Tum Manager ho. In parallel agent-outputs ko ek coherent action-plan me merge karo (4-5 line Hinglish).",
        f"Goal: {goal}\nOutputs: {json.dumps(results, ensure_ascii=False)[:2000]}",
        max_tokens=220,
        temperature=0.4,
    )
    out = {
        "ok": True,
        "goal": goal,
        "mode": "parallel",
        "agents": ags,
        "results": results,
        "summary": summary or "(merge abhi nahi bana)",
        "at": _now(),
    }
    _persist(out)
    return out


def _persist(rec: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_RUNS), exist_ok=True)
        with open(_RUNS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def recent_runs(limit: int = 20) -> list[dict]:
    out: list[dict] = []
    try:
        if os.path.exists(_RUNS):
            with open(_RUNS, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out[-limit:][::-1]


__all__ = ["roster", "plan", "coordinate", "fan_out", "recent_runs"]
