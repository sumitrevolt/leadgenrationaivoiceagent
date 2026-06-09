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


async def plan(goal: str, max_steps: int = 5, hint: str = "") -> list[dict]:
    """Goal -> ordered [{agent, task}] across allowlisted STAFF. Keyword fallback.

    `hint` = optional prior-learnings/reflection context (episodic memory) jo behtar
    plan ke liye condition karta (Reflexion).
    """
    roster_desc = "; ".join(f"{k}={v.get('title')}" for k, v in _roster().items())
    sys = (
        "Tum LeadGenAI ke Manager (Boss) ho. Goal ko 2-4 ORDERED sub-tasks me todo, har ek "
        "ek STAFF agent ko assign. SIRF JSON array lautao: "
        '[{"agent":"<key>","task":"<chhota Hinglish task>"}]. '
        f"Allowed keys: {', '.join(_AGENTS)}. Roster: {roster_desc}. Aur kuch mat likho."
    )
    user = f"Goal: {goal}"
    if hint:
        user += f"\nPichhle learnings (inhe dhyan me rakho): {hint[:600]}"
    raw, _ = await _llm(sys, user, max_tokens=300, temperature=0.2)
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


# =========================================================================== #
# ADVANCED ORCHESTRATION (2026 SOTA, free-stack native, NEVER raises):
#   - Reflexion loop : Actor (agents) -> Evaluator (critic) -> Self-Reflection -> retry
#                      (guardrails: max_iterations + quality_bar + convergence).
#   - Episodic memory (CoALA): verbal reflections persist + recall across runs.
#   - MAR critic     : Arjun (QA) ALAG persona grade kare (confirmation-bias kam).
#   - debate/consensus: pro vs con -> Boss judge.
# Research: Reflexion (Shinn 2023), MAR, CoALA memory, 2026 supervisor+reflection SOTA.
# =========================================================================== #
_MEMORY = os.path.join("data", "agent_memory.jsonl")
_MAX_MEM = 3  # Reflexion: bounded episodic buffer (1-3 reflections)


def memory_log(limit: int = 50) -> list[dict]:
    """Recent episodic memory (reflections + scores)."""
    out: list[dict] = []
    try:
        if os.path.exists(_MEMORY):
            with open(_MEMORY, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out[-limit:][::-1]


def _remember(topic: str, reflection: str, score: float) -> None:
    """Episodic memory write — verbal reflection + score (bounded, append-only)."""
    if not reflection:
        return
    try:
        os.makedirs(os.path.dirname(_MEMORY), exist_ok=True)
        with open(_MEMORY, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"topic": topic[:120], "reflection": reflection[:600], "score": score, "at": _now()},
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass


def _recall(topic: str, k: int = _MAX_MEM) -> list[str]:
    """Retrieve up to k most-relevant prior reflections (keyword overlap, semantic-lite)."""
    rows = memory_log(limit=200)
    toks = {w for w in topic.lower().split() if len(w) > 3}
    scored: list[tuple[int, str]] = []
    for r in rows:
        rt = str(r.get("topic", "")).lower()
        overlap = len(toks & {w for w in rt.split() if len(w) > 3})
        if overlap:
            scored.append((overlap, str(r.get("reflection", ""))))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:k] if r]


async def _verify(goal: str, results: list[dict]) -> dict:
    """Critic/Evaluator (Arjun=QA persona, MAR separation) → score 0-1 + weaknesses + fixes."""
    sys = (
        "Tum Arjun ho — QA Engineer (critic). Team ke kaam ko goal ke against kathorta se grade karo. "
        'SIRF JSON lautao: {"score":0.0-1.0,"weak":["..."],"fixes":["..."]}. '
        "score=kitna goal poora hua. weak=kya missing/kamzor. fixes=kya improve karna. Aur kuch nahi."
    )
    raw, _ = await _llm(
        sys,
        f"Goal: {goal}\nTeam results: {json.dumps(results, ensure_ascii=False)[:2000]}",
        max_tokens=240,
        temperature=0.2,
    )
    t = (raw or "").strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1 and j > i:
        t = t[i : j + 1]
    try:
        d = json.loads(t)
        score = float(d.get("score", 0.6))
        weak = d.get("weak") if isinstance(d.get("weak"), list) else []
        fixes = d.get("fixes") if isinstance(d.get("fixes"), list) else []
        return {"score": max(0.0, min(1.0, score)), "weak": weak[:5], "fixes": fixes[:5]}
    except Exception:
        # Neutral fallback — loop ko stuck/infinite hone se bachao.
        return {"score": 0.6, "weak": [], "fixes": []}


async def _reflect(goal: str, results: list[dict], critique: dict) -> str:
    """Self-Reflection module — verbal feedback: kya galat tha + agli baar kaise behtar."""
    out, _ = await _llm(
        "Tum reflective strategist ho. Critique dekh ke 2-3 line Hinglish reflection do: kya kamzor tha aur "
        "agli iteration me kaise improve karein. Sirf reflection text.",
        f"Goal: {goal}\nCritique: {json.dumps(critique, ensure_ascii=False)[:800]}",
        max_tokens=160,
        temperature=0.5,
    )
    return out


async def coordinate_advanced(
    goal: str,
    max_iterations: int = 2,
    quality_bar: float = 0.7,
    execute: bool = False,
    max_steps: int = 4,
) -> dict:
    """Reflexion orchestration: recall memory → plan → execute (handoff) → VERIFY (critic) →
    score<bar & iterations left ho to REFLECT + retry → aggregate.

    Guardrails: `max_iterations` (cap 3) + `quality_bar` (early-stop on convergence).
    Episodic memory persist (reflections). SAFE default (execute=False=drafts). Never raises.
    """
    goal = (goal or "").strip()
    if len(goal) < 3:
        return {"ok": False, "error": "goal bahut chhota hai"}
    run_id = uuid.uuid4().hex[:12]
    recalled = _recall(goal)
    hint = " | ".join(recalled)
    _log("manager", "advanced_start", f"{goal} (mem:{len(recalled)})")
    iterations: list[dict] = []
    results: list[dict] = []
    critique = {"score": 0.0, "weak": [], "fixes": []}
    reflection = ""
    for it in range(max(1, min(3, max_iterations))):
        steps = await plan(goal, max_steps=max_steps, hint=hint)
        bb: dict[str, Any] = {"goal": goal, "results": [], "reflection": reflection}
        for s in steps:
            r = await _run_agent(s["agent"], s["task"], bb, execute)
            bb["results"].append({"agent": s["agent"], "task": s["task"], **r})
            _log(s["agent"], "adv_step", f"{s['task']} [it{it}]")
        results = bb["results"]
        critique = await _verify(goal, results)
        iterations.append(
            {"iteration": it, "score": critique["score"], "weak": critique["weak"], "steps": len(steps)}
        )
        if critique["score"] >= quality_bar:
            break
        reflection = await _reflect(goal, results, critique)
        _remember(goal, reflection, critique["score"])
        hint = (hint + " | " + reflection)[:800]
    summary, _ = await _llm(
        "Tum Manager ho. Final team output + critique ko 3-4 line Hinglish summary + clear next-action me sameto. Sirf text.",
        f"Goal: {goal}\nResults: {json.dumps(results, ensure_ascii=False)[:1600]}\nCritique: {json.dumps(critique, ensure_ascii=False)[:600]}",
        max_tokens=220,
        temperature=0.4,
    )
    _log("manager", "advanced_done", f"score={critique['score']} iters={len(iterations)}")
    out = {
        "ok": True,
        "run_id": run_id,
        "goal": goal,
        "pattern": "reflexion",
        "iterations": iterations,
        "final_score": critique["score"],
        "critique": critique,
        "results": results,
        "summary": summary or "(summary abhi nahi bana)",
        "memory_used": len(recalled),
        "at": _now(),
    }
    _persist(out)
    return out


async def debate(question: str, rounds: int = 1) -> dict:
    """Consensus pattern — Rohan (pro) vs Kavya (con) argue, Boss judge decides. Never raises."""
    question = (question or "").strip()
    if len(question) < 3:
        return {"ok": False, "error": "question bahut chhota hai"}
    transcript: list[dict] = []
    pro = con = ""
    for rd in range(max(1, min(2, rounds))):
        pro, _ = await _llm(
            "Tum Rohan ho. Is proposal ke PRO me 2-3 line strong argument do (Hinglish).",
            f"Proposal: {question}\nOpponent abhi tak: {con}",
            max_tokens=160,
            temperature=0.6,
        )
        con, _ = await _llm(
            "Tum Kavya ho. Is proposal ke AGAINST/risks 2-3 line me do (Hinglish).",
            f"Proposal: {question}\nProponent: {pro}",
            max_tokens=160,
            temperature=0.6,
        )
        transcript.append({"round": rd, "pro": pro, "con": con})
    verdict, _ = await _llm(
        "Tum Manager (Boss) ho. Dono side dekh ke ek CLEAR decision + reason do (3-4 line Hinglish).",
        f"Proposal: {question}\nDebate: {json.dumps(transcript, ensure_ascii=False)[:1600]}",
        max_tokens=200,
        temperature=0.3,
    )
    out = {"ok": True, "question": question, "rounds": transcript, "verdict": verdict or "(verdict nahi bana)", "at": _now()}
    _persist(out)
    return out


__all__ = [
    "roster",
    "plan",
    "coordinate",
    "coordinate_advanced",
    "fan_out",
    "debate",
    "recent_runs",
    "memory_log",
]
