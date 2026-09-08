"""Multi-agent COORDINATOR — free-stack, always-on coordination over the STAFF roster.

Existing pieces (REBUILD NAHI): `team.STAFF` (31-staff roster), `staff.py` (concrete
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
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RUNS = os.path.join("data", "coordination_runs.jsonl")
# Legacy fallback if STAFF import fails.
_LEGACY_AGENTS = ("manager", "rohan", "swara", "dev", "arjun", "meera", "kavya", "isha")


def _agent_keys() -> tuple[str, ...]:
    """All STAFF keys — planner may assign any; execute uses _TOOLS subset."""
    roster = _roster()
    return tuple(roster.keys()) if roster else _LEGACY_AGENTS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _roster() -> dict[str, dict]:
    try:
        from app.platform.team import STAFF

        return STAFF
    except Exception:
        return {}


def _guess_niche(text: str) -> str:
    """Loose keyword-match goal/task → a configured niche key (fallback 'general')."""
    try:
        from app.niches import NICHES

        t = (text or "").lower()
        for k, v in (NICHES or {}).items():
            name = str((v or {}).get("name", k)).lower()
            if k.replace("_", " ") in t or (name and name in t):
                return k
        for k, v in (NICHES or {}).items():
            name = str((v or {}).get("name", k)).lower()
            if any(w in t for w in name.split() if len(w) > 3):
                return k
    except Exception:
        pass
    return "general"


# --------------------------------------------------------------------------- #
# Per-agent REAL tools (execute-mode): goal-aware, ACTUAL artifacts produce karte
# (sirf draft nahi). SAFE only — koi auto-send/call nahi. Side-effect agents
# (rohan=outreach, swara=calls) jaan-bujhke OUT → woh draft hi rehte (ban-safe).
# --------------------------------------------------------------------------- #
async def _tool_isha(task: str, goal: str) -> dict:
    """Marketing — real social post (caption + hashtags + image idea)."""
    from app.marketing import post_generator

    p = await post_generator.generate_post(
        business_name="Aapka Business", niche=_guess_niche(goal + " " + task), occasion=task[:80]
    )
    return {
        "tool": "generate_post",
        "caption": p.get("caption"),
        "hashtags": p.get("hashtags"),
        "image_idea": p.get("image_idea"),
    }


async def _tool_dev(task: str, goal: str) -> dict:
    """Data/research — real trending hashtags + best-time research for the niche."""
    from app.marketing import hashtags

    h = await hashtags.research(_guess_niche(goal + " " + task), "", count=12)
    return {"tool": "hashtags.research", "research": h if isinstance(h, dict) else {"data": h}}


async def _tool_kavya(task: str, goal: str) -> dict:
    """Ops — real system health snapshot."""
    from app.agents import staff

    return {"tool": "run_ops", "result": await staff.run_ops()}


async def _tool_arjun(task: str, goal: str) -> dict:
    """QA — real agent scorecard run."""
    from app.agents import staff

    return {"tool": "run_qa", "result": await staff.run_qa()}


async def _tool_meera(task: str, goal: str) -> dict:
    """Trainer — real transcript-quality analysis."""
    from app.agents import staff

    return {"tool": "run_trainer", "result": await staff.run_trainer()}


# agent -> real goal-aware tool (execute mode). manager/rohan/swara = draft-only.
_TOOLS: dict[str, Any] = {
    "isha": _tool_isha,
    "dev": _tool_dev,
    "kavya": _tool_kavya,
    "arjun": _tool_arjun,
    "meera": _tool_meera,
}


def roster() -> list[dict]:
    """Public roster + which agents have a real executable tool (execute-mode)."""
    return [
        {
            "id": k,
            "name": v.get("name"),
            "title": v.get("title"),
            "duties": v.get("duties"),
            "executable": k in _TOOLS,
        }
        for k, v in _roster().items()
    ]


def _log(member: str, action: str, detail: str) -> None:
    try:
        from app.platform.team import log_event

        log_event(member, action, (detail or "")[:180])
    except Exception:
        pass


def _heartbeat(pattern: str, ok: bool, t0: float, note: str = "") -> None:
    """Feed dead-man /automation_health (team.log_event alone overdue-alert nahi kholta)."""
    try:
        from app.platform import automation_health

        automation_health.record_run(
            "coordinator",
            ok=bool(ok),
            seconds=max(0.0, time.monotonic() - t0),
            note=f"{pattern}:{(note or '')}"[:120],
        )
    except Exception:
        pass


# --- D2: coordinator LLM cost guard (INERT unless COORDINATOR_LLM_CAP_PER_MIN>0) ---
# self_improve ke paas SELFIMPROVE_COST_CAP hai; coordinator ke LLM calls (plan/
# coordinate/fan_out/reflect/debate) ka koi cap nahi tha — recurring/public path me
# unbounded cost risk. Yeh rolling 60s-window rate-cap deta: over-budget pe call SKIP
# (fail-open — empty reply, callers already graceful). cap<=0 = default unchanged.
_LLM_WINDOW: dict[str, float] = {"start": 0.0, "count": 0.0}


def _llm_rate_ok() -> bool:
    try:
        cap = int(os.environ.get("COORDINATOR_LLM_CAP_PER_MIN", "60") or "60")
    except Exception:
        cap = 0
    if cap <= 0:
        return True  # INERT — behaviour unchanged
    now = time.monotonic()
    if now - _LLM_WINDOW["start"] >= 60.0:
        _LLM_WINDOW["start"] = now
        _LLM_WINDOW["count"] = 0.0
    if _LLM_WINDOW["count"] >= cap:
        return False
    _LLM_WINDOW["count"] += 1.0
    return True


async def _llm(system: str, user: str, max_tokens: int = 260, temperature: float = 0.4):
    if not _llm_rate_ok():
        logger.info("coordinator LLM rate-cap reached — skipping call (fail-open)")
        return "", "rate_capped"
    # COORD_GUARDRAILS (OFF default, INERT): PRE-LLM PII-redact + injection-block on
    # the user prompt, POST-LLM system-leak/unsafe-promise block on the reply.
    # Voice path (natural_dialog) already guards its brain; the agent/coordinator
    # LLM path was the unwired one. Fail-open — guardrail error = original text.
    grd = None
    if os.environ.get("COORD_GUARDRAILS", "").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from app.voice_agent.guardrails import get_guardrails

            grd = get_guardrails()
            _in = grd.check_input(user or "")
            if not _in.allowed:
                logger.info("coordinator guardrail blocked input: %s", _in.violations)
                return "", "guardrail_blocked"
            user = _in.text
        except Exception as e:  # pragma: no cover - fail-open
            logger.debug("coordinator guardrails pre-check skip: %s", e)
    try:
        from app.voice_agent import free_ai

        reply, prov = await free_ai.chat(
            system,
            [{"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        reply = (reply or "").strip()
        if grd is not None:
            try:
                _out = grd.check_output(reply)
                reply = (_out.text if _out.allowed else _SAFE_OUTPUT_FALLBACK) or reply
                if not _out.allowed:
                    logger.info("coordinator guardrail blocked output: %s", _out.violations)
            except Exception as e:  # pragma: no cover - fail-open
                logger.debug("coordinator guardrails post-check skip: %s", e)
        return reply, prov
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("coordinator llm err: %s", e)
        return "", "none"


_SAFE_OUTPUT_FALLBACK = (
    "Mujhe is baar is sawaal ka confident jawab nahi mila. Aage ka kaam baki team kar sakti hai."
)


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


# --- ADR-159 MetaGPT steal-#1: structured plan canary (INERT unless COORD_PLAN_NODE) ---
# coordinator._extract_list() scrapes freeform JSON and silently drops to a hardcoded
# chain on junk. plan_node.structured_plan runs the ActionNode fill -> review -> revise
# cycle over a typed schema; on success it wins, on any failure we fall through to the
# legacy parse + hardcoded chain unchanged. The injected llm_fn=_llm honours the
# COORDINATOR_LLM_CAP_PER_MIN rate-cap and the free_ai circuit breaker.


def _plan_node_enabled() -> bool:
    return os.environ.get("COORD_PLAN_NODE", "").strip().lower() in ("1", "true", "yes", "on")


def _plan_node_reviews() -> int:
    try:
        return max(0, int(os.environ.get("COORD_PLAN_NODE_REVIEWS", "1") or "1"))
    except Exception:
        return 1


def _memory_canary_on() -> bool:
    """Dedicated canary flag for the memory-stack context path (default OFF).

    OFF = byte-identical legacy behaviour (`hint[:600]`). Subordinate to the
    memory stack's own master flag — canary alone can never turn it on.
    """
    if (os.environ.get("MEMORY_STACK_COORDINATOR_CANARY", "").strip().lower()) not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    try:
        from app.platform import memory_stack

        return memory_stack.is_enabled()
    except Exception:
        return False


async def _plan_context(goal: str, hint: str) -> str:
    """Canary: token-budgeted memory block; ANY problem => legacy hint slice.

    Never raises and never blocks planning — a memory miss degrades to exactly
    what the legacy path would have produced.
    """
    legacy = f"\nPichhle learnings (inhe dhyan me rakho): {hint[:600]}" if hint else ""
    if not _memory_canary_on():
        return legacy
    try:
        from app.platform import memory_stack

        block = await memory_stack.assemble_block(
            os.environ.get("MEMORY_STACK_PLATFORM_TENANT", "platform"),
            "coordinator",
            goal,
            token_budget=int(os.environ.get("MEMORY_STACK_COORDINATOR_TOKENS", "300") or 300),
        )
        if not (block or "").strip():
            return legacy  # empty recall = legacy, not a silently emptier prompt
        return f"\nYaaddasht (memory stack):\n{block}" + legacy
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("coordinator memory-stack canary fell back to legacy: %s", e)
        return legacy


async def plan(goal: str, max_steps: int = 5, hint: str = "") -> list[dict]:
    """Goal -> ordered [{agent, task}] across allowlisted STAFF. Keyword fallback.

    `hint` = optional prior-learnings/reflection context (episodic memory) jo behtar
    plan ke liye condition karta (Reflexion). Canary flag ON ho to yeh hint ke
    saath memory-stack ka budgeted block bhi jodta hai (fallback = legacy).
    """
    roster_desc = "; ".join(f"{k}={v.get('title')}" for k, v in _roster().items())
    sys = (
        "Tum LeadGenAI ke Manager (Boss) ho. Goal ko 2-4 ORDERED sub-tasks me todo, har ek "
        "ek STAFF agent ko assign. SIRF JSON array lautao: "
        '[{"agent":"<key>","task":"<chhota Hinglish task>"}]. '
        f"Allowed keys: {', '.join(_agent_keys())}. Roster: {roster_desc}. Aur kuch mat likho."
    )
    user = f"Goal: {goal}"
    user += await _plan_context(goal, hint)
    # Inject obsidian second brain context (past decisions/patterns)
    try:
        from app.platform import obsidian_sync as _obs

        _brain = _obs.brain_context(str(goal or ""))
        if _brain:
            user = user + "\n\n" + _brain
    except Exception:
        pass
    # Hivemind READ path: skills KB se past successful patterns retrieve karo
    if os.environ.get("COORD_KB_SHARE", "").strip() in ("1", "true", "yes", "on"):
        try:
            from app.voice_agent.knowledge_base import get_knowledge_base

            _kb = get_knowledge_base()
            _skill_hits = await asyncio.wait_for(
                asyncio.to_thread(lambda: _kb.search(goal[:300], namespace="skills", top_k=3)),
                timeout=3.0,
            )
            if _skill_hits:
                _skill_ctx = "\n".join(
                    h.get("text", "") or h.get("content", "") for h in _skill_hits if h
                )[:600]
                if _skill_ctx.strip():
                    user += f"\nPichhle successful patterns (KB skills):\n{_skill_ctx}"
        except Exception:
            pass
    # ADR-159 canary: structured fill/review/revise BEFORE the legacy call so the
    # failure path (and only it) costs the extra LLM call. INERT unless COORD_PLAN_NODE.
    if _plan_node_enabled():
        try:
            from app.agents.harness import plan_node as _pn

            _res = await _pn.structured_plan(
                goal=goal,
                system=sys,
                user=user,
                allowed_agents=_agent_keys(),
                llm_fn=_llm,
                max_review_rounds=_plan_node_reviews(),
                max_steps=max_steps,
            )
            if _res and _res.get("steps"):
                logger.info(
                    "manager plan_node adopted (%s, reviews=%s) for goal %.60r",
                    _res.get("source"),
                    _res.get("reviews"),
                    goal,
                )
                return _res["steps"]
            logger.info("manager plan_node produced no plan — legacy fallback")
        except Exception as e:  # defensive — canary never breaks plan()
            logger.debug("manager plan_node canary err: %s", e)
    raw, _ = await _llm(sys, user, max_tokens=300, temperature=0.2)
    steps = [
        {"agent": s["agent"], "task": str(s["task"])[:240]}
        for s in _extract_list(raw)
        if isinstance(s, dict) and s.get("agent") in _agent_keys() and s.get("task")
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
    if execute and agent in _TOOLS:
        _t0 = time.monotonic()
        _res = None
        _err = None
        try:
            _res = await _TOOLS[agent](task, blackboard.get("goal", ""))
            _out = {"mode": "executed", "output": _res}
        except Exception as e:  # pragma: no cover - defensive
            _err = str(e)[:200]
            _out = {"mode": "executed", "error": _err}
        # Harness coordinator shadow (record-only; INERT unless AGENT_HARNESS +
        # AGENT_HARNESS_SHADOW on, delegated agent in canary agents, coordinator
        # in canary loops). agent_id = the REAL delegated agent. NEVER re-executes
        # the tool, never calls the LLM, never changes the coordinator result.
        try:
            from app.agents.harness.adapters import observe_coordinator_action

            observe_coordinator_action(
                coordinator_run_id=str(blackboard.get("_run_id") or ""),
                orchestration_path=str(blackboard.get("_path") or "coordinate"),
                action_index=len(blackboard.get("results", [])),
                agent_id=agent,
                tenant_id=str(blackboard.get("_tenant") or ""),
                normalized_action={"tool": agent, "task": task},
                actual_executor=(
                    (_res.get("tool") if isinstance(_res, dict) else "") or f"_TOOLS[{agent}]"
                ),
                actual_result=(_res if _err is None else None),
                actual_error=_err,
                latency_ms=round((time.monotonic() - _t0) * 1000, 1),
            )
        except Exception:
            pass
        return _out
    # Budget governor on the DRAFT/LLM branch (the execute branch above already ran under
    # staff's own governance at app/agents/staff.py:1436 — don't change its behaviour).
    # fan_out/agentverse/debate/council issue one LLM call per agent per round, and
    # _llm_rate_ok() caps burst-per-minute, NOT the daily total. Without this a swarm can
    # eat the day's free-tier quota (Groq TPD) that the revenue-bearing voice path shares.
    # INERT by construction: check() returns allowed=True when AGENT_BUDGET_ENABLED is off.
    # Fail-OPEN — a budget-subsystem error must never block the agent.
    try:
        from app.platform import agent_budget

        _b = agent_budget.check(agent)
        if not _b.get("allowed", True):
            logger.info(
                "coordinator: %s skipped — budget exceeded (tier %s)", agent, _b.get("tier")
            )
            return {"mode": "skipped", "reason": "budget_exceeded", "budget": _b, "output": ""}
    except Exception:
        pass
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
    return {
        "mode": "draft",
        "output": out or f"({agent} ka draft abhi nahi bana)",
        "provider": prov,
    }


def _build_handoff_meta(agent: str, seq: int, res: dict) -> dict:
    """Additive handoff metadata for the shared blackboard (Item B). Bounded +
    PII-redacted context_preview so the NEXT agent's prompt never inherits raw
    PII across a handoff. Fail-open: guardrail error = bounded plain text."""
    try:
        from app.voice_agent.guardrails import get_guardrails

        _txt = json.dumps(
            {k: v for k, v in (res or {}).items() if k != "handoff"},
            ensure_ascii=False,
            default=str,
        )
        _red = get_guardrails().redact_pii(_txt)
        return {
            "from_agent": agent,
            "seq": int(seq),
            "context_preview": _red[:600],
        }
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("coordinator handoff meta skip: %s", e)
        return {"from_agent": agent, "seq": int(seq), "context_preview": ""}


async def coordinate(goal: str, execute: bool = False, max_steps: int = 5) -> dict:
    """Plan -> sequential handoff over agents (shared blackboard) -> Boss aggregate.

    SAFE default (execute=False = drafts, koi side-effect nahi). Never raises.
    """
    goal = (goal or "").strip()
    if len(goal) < 3:
        return {"ok": False, "error": "goal bahut chhota hai"}
    t0 = time.monotonic()
    run_id = uuid.uuid4().hex[:12]
    steps = await plan(goal, max_steps)
    blackboard: dict[str, Any] = {"goal": goal, "results": []}
    blackboard["_run_id"] = run_id  # harness shadow correlation (record-only)
    blackboard["_path"] = "coordinate"
    _log("manager", "coordinate_start", f"{goal} -> {len(steps)} steps")
    for s in steps:
        agent, task = s["agent"], s["task"]
        res = await _run_agent(agent, task, blackboard, execute)
        _handoff = _build_handoff_meta(agent, len(blackboard.get("results", [])), res)
        blackboard["results"].append({"agent": agent, "task": task, "handoff": _handoff, **res})
        _log(agent, "coordinated_step", f"{task} [{res.get('mode')}]")
    summary, _ = await _llm(
        "Tum Manager (Boss) ho. Team ke kaam ko 3-4 line Hinglish summary + ek clear next-action me sameto. Sirf text.",
        f"Goal: {goal}\nTeam results: {json.dumps(blackboard['results'], ensure_ascii=False)[:2000]}",
        max_tokens=220,
        temperature=0.4,
    )
    _log("manager", "coordinate_done", summary or "done")
    # Hivemind: executed steps with success → KB skills namespace (cross-agent sharing)
    if os.environ.get("COORD_KB_SHARE", "").strip() in ("1", "true", "yes", "on"):
        _executed_ok = [
            r
            for r in blackboard.get("results", [])
            if r.get("mode") == "executed" and not r.get("error")
        ]
        if _executed_ok and summary:
            try:
                from app.voice_agent.knowledge_base import get_knowledge_base

                _kb = get_knowledge_base()
                _skill_text = f"Goal: {goal[:200]}\nOutcome: {(summary or '')[:400]}"
                await asyncio.to_thread(
                    lambda: _kb.add_documents(
                        [{"text": _skill_text, "source": f"coordinator:{run_id}"}],
                        namespace="skills",
                    )
                )
            except Exception:
                pass
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
    _heartbeat("coordinate", bool(summary), t0, goal[:60])
    return out


async def fan_out(goal: str, agents: list[str] | None = None, max_agents: int = 4) -> dict:
    """Parallel coordination — multiple agents ek saath (asyncio.gather), phir aggregate."""
    goal = (goal or "").strip()
    if len(goal) < 3:
        return {"ok": False, "error": "goal bahut chhota hai"}
    ags = [a for a in (agents or ["dev", "rohan", "isha", "kavya"]) if a in _agent_keys()][
        :max_agents
    ]
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
                    {
                        "topic": topic[:120],
                        "reflection": reflection[:600],
                        "score": score,
                        "at": _now(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # ADR-154: dual-write into workforce hub for Boss (manager) — fail-open.
    try:
        from app.platform import workforce_memory as _wfm

        _wfm.remember_reflection_bridge(topic, reflection, score=score, agent="manager")
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
    t0 = time.monotonic()
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
            {
                "iteration": it,
                "score": critique["score"],
                "weak": critique["weak"],
                "steps": len(steps),
            }
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
    # Obsidian — log reflexion run to Decisions/ (INERT if OBSIDIAN_SYNC unset).
    try:
        from app.platform import obsidian_sync as _obs

        _obs.write_note(
            "Decisions",
            f"reflexion-{run_id}",
            f"# Reflexion: {goal[:80]}\n\n**Score:** {critique['score']}\n**Iterations:** {len(iterations)}\n\n## Summary\n{out['summary']}",
            tags=["coordinator", "reflexion"],
        )
    except Exception:
        pass
    _heartbeat("advanced", bool(summary), t0, goal[:60])
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
    out = {
        "ok": True,
        "question": question,
        "rounds": transcript,
        "verdict": verdict or "(verdict nahi bana)",
        "at": _now(),
    }
    _persist(out)
    # Obsidian — log debate verdict to Decisions/ (INERT if OBSIDIAN_SYNC unset).
    try:
        from app.platform import obsidian_sync as _obs

        _obs.write_note(
            "Decisions",
            f"debate-{_now()[:10]}-{question[:30].replace(' ', '-')}",
            f"# Debate: {question[:100]}\n\n## Verdict\n{out['verdict']}\n\n**Rounds:** {len(transcript)}",
            tags=["coordinator", "debate"],
        )
    except Exception:
        pass
    return out


# =========================================================================== #
# HIERARCHICAL orchestration (2026 supervisor→sub-supervisor→workers topology).
# Boss goal ko relevant DOMAIN sub-teams me baantta; har sub-team ka supervisor
# apne members ko coordinate karta (teams PARALLEL); Boss top-level merge.
# =========================================================================== #
_LEGACY_TEAMS: dict[str, list[str]] = {
    "growth": ["dev", "rohan", "isha"],  # research + outreach + marketing
    "ops": ["kavya", "arjun", "meera"],  # health + QA + training
    "sales": ["rohan", "swara"],  # outreach + close
}


def coordination_topology() -> dict[str, Any]:
    """31/31 Boss-routing projection; never dispatches or widens rollout."""
    try:
        from app.platform.office_hq import coordination_topology as _topology

        return _topology()
    except Exception as exc:
        members = sorted({"manager", *[m for rows in _LEGACY_TEAMS.values() for m in rows]})
        return {
            "boss": "manager",
            "teams": [
                {"id": key, "name": key, "purpose": key, "members": list(value)}
                for key, value in _LEGACY_TEAMS.items()
            ],
            "staff_count": len(_agent_keys()),
            "covered_count": len(members),
            "coverage_ok": False,
            "missing_agents": sorted(set(_agent_keys()) - set(members)),
            "error": type(exc).__name__,
        }


def _coordination_teams() -> dict[str, list[str]]:
    rows = coordination_topology().get("teams") or []
    teams = {
        str(row.get("id")): [str(member) for member in (row.get("members") or [])]
        for row in rows
        if row.get("id") and row.get("members")
    }
    return teams or dict(_LEGACY_TEAMS)


async def _assign_teams(goal: str) -> dict[str, str]:
    """Boss decides which sub-team(s) handle the goal + each team's objective."""
    topology = coordination_topology()
    teams = _coordination_teams()
    catalog = "; ".join(
        f"{row.get('id')}({row.get('purpose')})" for row in (topology.get("teams") or [])
    )
    sys = (
        "Tum Manager (Boss) ho. Goal ke liye 1-3 relevant domain teams chuno aur har ek ka "
        "chhota objective do. SIRF JSON object lautao; keys sirf allowed team ids hon. "
        f"Allowed teams: {', '.join(teams)}. Catalog: {catalog}. Aur kuch nahi."
    )
    raw, _ = await _llm(sys, f"Goal: {goal}", max_tokens=200, temperature=0.2)
    t = (raw or "").strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1 and j > i:
        t = t[i : j + 1]
    try:
        d = json.loads(t)
        out = {k: str(v)[:200] for k, v in d.items() if k in teams and v}
        if out:
            return out
    except Exception:
        pass
    fallback = "marketing_team" if "marketing_team" in teams else next(iter(teams), "growth")
    return {fallback: goal}


async def _run_team(team: str, objective: str, execute: bool) -> dict:
    """Sub-supervisor: team ke members ko sequential handoff se coordinate kare."""
    members = _coordination_teams().get(team, [])
    bb: dict[str, Any] = {"goal": objective, "results": []}
    for m in members:
        v = _roster().get(m, {})
        r = await _run_agent(m, f"{objective} ({v.get('title', '')})", bb, execute)
        bb["results"].append({"agent": m, **r})
        _log(m, "hier_step", f"{team}: {objective[:80]}")
    sub, _ = await _llm(
        f"Tum {team} team ke supervisor ho. Apni team ke kaam ko 2-3 line Hinglish me sameto. Sirf text.",
        f"Objective: {objective}\nResults: {json.dumps(bb['results'], ensure_ascii=False)[:1400]}",
        max_tokens=160,
        temperature=0.4,
    )
    return {
        "team": team,
        "objective": objective,
        "members": members,
        "results": bb["results"],
        "summary": sub or "(team summary nahi bana)",
    }


async def coordinate_hierarchical(goal: str, execute: bool = False) -> dict:
    """2-level hierarchy: Boss → sub-teams (PARALLEL) → members → Boss merge. Never raises."""
    goal = (goal or "").strip()
    if len(goal) < 3:
        return {"ok": False, "error": "goal bahut chhota hai"}
    t0 = time.monotonic()
    run_id = uuid.uuid4().hex[:12]
    assign = await _assign_teams(goal)
    _log("manager", "hier_start", f"{goal} -> teams {list(assign)}")
    team_outs = await asyncio.gather(
        *[_run_team(t, obj, execute) for t, obj in assign.items()], return_exceptions=True
    )
    teams = [t for t in team_outs if isinstance(t, dict)]
    summary, _ = await _llm(
        "Tum Manager (Boss) ho. Sub-teams ke summaries ko ek unified 4-5 line Hinglish plan + next-action me merge karo. Sirf text.",
        f"Goal: {goal}\nTeams: {json.dumps([{'team': t['team'], 'summary': t['summary']} for t in teams], ensure_ascii=False)[:1600]}",
        max_tokens=240,
        temperature=0.4,
    )
    _log("manager", "hier_done", summary or "done")
    assignments = [
        {
            "team": team.get("team"),
            "objective": team.get("objective"),
            "members": list(team.get("members") or []),
        }
        for team in teams
    ]
    handoffs: list[dict[str, Any]] = []
    for team in teams:
        team_id = str(team.get("team") or "")
        handoffs.append(
            {
                "from": "manager",
                "to": f"team:{team_id}",
                "status": "assigned",
                "evidence": str(team.get("objective") or "")[:200],
            }
        )
        for result in team.get("results") or []:
            failed = bool(result.get("error")) or result.get("mode") == "skipped"
            handoffs.append(
                {
                    "from": f"team:{team_id}",
                    "to": str(result.get("agent") or ""),
                    "status": "blocked" if failed else "completed",
                    "mode": str(result.get("mode") or "unknown"),
                    "evidence": str(result.get("error") or result.get("output") or "")[:240],
                }
            )
    verdict_status = (
        "completed"
        if teams and summary and all(handoff.get("status") != "blocked" for handoff in handoffs)
        else ("partial" if teams else "incomplete")
    )
    topology = coordination_topology()
    out = {
        "ok": True,
        "run_id": run_id,
        "goal": goal,
        "pattern": "hierarchical",
        "execute": execute,
        "boss": "manager",
        "teams": teams,
        "assignments": assignments,
        "handoffs": handoffs,
        "verdict": {
            "by": "manager",
            "status": verdict_status,
            "summary": summary or "(merge nahi bana)",
            "owner_gate": "manual_upi_credit_confirmation_only",
            "system_hard_gates": "unchanged",
        },
        "coordination_coverage": {
            "staff_count": topology.get("staff_count"),
            "covered_count": topology.get("covered_count"),
            "coverage_ok": topology.get("coverage_ok"),
        },
        "summary": summary or "(merge nahi bana)",
        "at": _now(),
    }
    _persist(out)
    # Obsidian — log hierarchical run to Decisions/ (INERT if OBSIDIAN_SYNC unset).
    try:
        from app.platform import obsidian_sync as _obs

        _obs.write_note(
            "Decisions",
            f"hier-{run_id}",
            f"# Hierarchical: {goal[:80]}\n\n## Summary\n{out['summary']}",
            tags=["coordinator", "hierarchical"],
        )
    except Exception:
        pass
    _heartbeat("hierarchical", bool(summary), t0, goal[:60])
    # Governed decision adapters (INERT unless BOSS_DECISION_GOVERNANCE=1)
    try:
        from app.platform import boss_decision_governance as _bdg

        out["governance"] = _bdg.propose_from_hierarchical_run(out)
    except Exception as e:
        out["governance"] = {"ok": False, "error": type(e).__name__, "inert_safe": True}
    return out


# --------------------------------------------------------------------------- #
# AgentVerse-style task-solving (OpenBMB, ICLR'24 — arXiv:2308.10848).
# 4-stage CLOSED LOOP: RECRUIT (dynamic, task-tailored experts) → COLLABORATE
# (experts contribute + solver synthesizes) → EXECUTE (safe staff tools, execute=True)
# → EVALUATE (_verify) → feedback se team RE-COMPOSE + refine (rounds tak).
# coordinate_advanced (FIXED roster Reflexion) se ALAG: yahan team khud goal ke hisaab
# se banti hai aur evaluator-feedback pe har round badalti (AgentVerse ka signature).
# All free-stack (free_ai), reuses _verify/_recall/_remember/_persist. NEVER raises.
# --------------------------------------------------------------------------- #
async def _recruit_experts(goal: str, feedback: str = "", team_size: int = 3) -> list[dict]:
    """Stage 1 — RECRUITER (HR-manager persona) goal ke liye 2-4 TAILORED expert roles
    design karta (fixed roster nahi). feedback (evaluator se) team ko RE-COMPOSE karta."""
    staff_keys = ", ".join(_agent_keys())
    sys = (
        "Tum ek RECRUITER ho (HR manager jaisa). Goal ke liye 2-4 EXPERT roles design karo jo "
        "milke ise best solve karein — roles goal ke hisaab se TAILORED hon (generic nahi). "
        'SIRF JSON array lautao: [{"role":"<expert title>","expertise":"<1-line kya laata hai>",'
        f'"staff":"<closest in {staff_keys}, warna khaali>"}}]. Aur kuch mat likho.'
    )
    user = f"Goal: {goal}"
    if feedback:
        user += f"\nPichhli round ka evaluator-feedback (team isi hisaab se ADJUST karo): {feedback[:600]}"
    raw, _ = await _llm(sys, user, max_tokens=320, temperature=0.5)
    experts: list[dict] = []
    for e in _extract_list(raw):
        if isinstance(e, dict) and e.get("role"):
            staff = str(e.get("staff") or "").strip().lower()
            experts.append(
                {
                    "role": str(e["role"])[:80],
                    "expertise": str(e.get("expertise") or "")[:160],
                    "staff": staff if staff in _agent_keys() else "",
                }
            )
    experts = experts[: max(2, min(4, team_size))]
    if experts:
        return experts
    return [  # fallback trio (LLM down/parse fail)
        {"role": "Domain Researcher", "expertise": "niche + market grounding", "staff": "dev"},
        {"role": "Strategy Lead", "expertise": "plan + prioritization", "staff": "manager"},
        {"role": "Execution Specialist", "expertise": "concrete deliverable", "staff": "isha"},
    ][: max(2, min(4, team_size))]


async def _expert_contribution(expert: dict, goal: str, board: str, execute: bool) -> dict:
    """Stage 2/3 — ek recruited expert apna perspective de. execute + staff-bound + real
    tool ho to ACTUAL artifact (safe capability), warna free-LLM draft."""
    staff = expert.get("staff") or ""
    if execute and staff in _TOOLS:
        _t0 = time.monotonic()
        _res = None
        _err = None
        try:
            _res = await _TOOLS[staff](goal, goal)
            _out = {"role": expert["role"], "staff": staff, "mode": "executed", "output": _res}
        except Exception as e:  # pragma: no cover - defensive
            _err = str(e)[:200]
            _out = {"role": expert["role"], "staff": staff, "mode": "executed", "error": _err}
        # Harness coordinator shadow — SECOND executor boundary (_expert_contribution).
        # Record-only; INERT unless canary flags on. NEVER re-runs the tool, never
        # changes the contribution, never raises.
        try:
            from app.agents.harness.adapters import observe_coordinator_action

            observe_coordinator_action(
                coordinator_run_id="coord_expert_" + str(abs(hash(goal)) % 10**8),
                orchestration_path="agentverse",
                action_index=0,
                agent_id=staff,
                tenant_id="",
                normalized_action={"tool": staff, "task": str(expert.get("role") or "")[:120]},
                actual_executor=(
                    (_res.get("tool") if isinstance(_res, dict) else "") or f"_TOOLS[{staff}]"
                ),
                actual_result=(_res if _err is None else None),
                actual_error=_err,
                latency_ms=round((time.monotonic() - _t0) * 1000, 1),
                boundary="_expert_contribution",
            )
        except Exception:
            pass
        return _out
    sys = (
        f"Tum '{expert['role']}' ho — expertise: {expert.get('expertise', '')}. Apne expert lens se "
        "goal pe concrete, actionable contribution do (3-5 line Hinglish). Sirf apna output."
    )
    out, prov = await _llm(
        sys, f"Goal: {goal}\nAb tak team ne: {board[:1200]}", max_tokens=240, temperature=0.5
    )
    return {
        "role": expert["role"],
        "staff": staff,
        "mode": "draft",
        "output": out or "(draft pending)",
        "provider": prov,
    }


async def _solver_synthesize(goal: str, contributions: list[dict], feedback: str = "") -> str:
    """Stage 2 (vertical solver) — experts ke contributions ko ek coherent, actionable
    SOLUTION me synthesize karo (evaluator feedback ko address karte hue)."""
    sys = (
        "Tum SOLVER ho. Experts ke contributions ko ek single, coherent, actionable SOLUTION me "
        "synthesize karo (5-8 line Hinglish, clear steps). feedback diya ho to use address karo. Sirf solution."
    )
    user = f"Goal: {goal}\nExpert contributions: {json.dumps(contributions, ensure_ascii=False)[:2000]}"
    if feedback:
        user += f"\nEvaluator feedback (isse fix karo): {feedback[:500]}"
    out, _ = await _llm(sys, user, max_tokens=420, temperature=0.45)
    return out


async def coordinate_agentverse(
    goal: str,
    execute: bool = False,
    max_rounds: int = 2,
    quality_bar: float = 0.75,
    team_size: int = 3,
) -> dict:
    """AgentVerse task-solving loop (arXiv:2308.10848): RECRUIT → COLLABORATE+SOLVE →
    EXECUTE → EVALUATE → feedback se team RE-COMPOSE + refine (rounds tak, best-of kept).

    Guardrails: max_rounds (cap 3) + quality_bar (early-stop). Episodic memory (_recall/
    _remember) cross-run learning. SAFE default (execute=False=drafts). Never raises.
    """
    goal = (goal or "").strip()
    if len(goal) < 3:
        return {"ok": False, "error": "goal bahut chhota hai"}
    run_id = uuid.uuid4().hex[:12]
    recalled = _recall(goal)
    feedback = " | ".join(recalled)
    _log("manager", "agentverse_start", f"{goal} (mem:{len(recalled)})")
    rounds: list[dict] = []
    best: dict[str, Any] = {
        "solution": "",
        "score": -1.0,
        "experts": [],
        "critique": {},
        "contributions": [],
    }
    for rnd in range(max(1, min(3, max_rounds))):
        experts = await _recruit_experts(goal, feedback=feedback, team_size=team_size)
        _log("manager", "av_recruit", f"r{rnd}: " + ", ".join(e["role"] for e in experts))
        board = ""
        contributions: list[dict] = []
        for ex in experts:  # collaborative — har expert pichhla board dekhta (shared context)
            c = await _expert_contribution(ex, goal, board, execute)
            contributions.append(c)
            board += f"\n[{c['role']}] {json.dumps(c.get('output'), ensure_ascii=False)[:400]}"
            _log(ex.get("staff") or "manager", "av_contrib", f"{ex['role']} [r{rnd}]")
        solution = await _solver_synthesize(goal, contributions, feedback=feedback if rnd else "")
        critique = await _verify(goal, [{"solution": solution, "contributions": contributions}])
        score = float(critique.get("score", 0.6))
        rounds.append(
            {
                "round": rnd,
                "experts": [{"role": e["role"], "staff": e.get("staff", "")} for e in experts],
                "score": score,
                "weak": critique.get("weak", []),
            }
        )
        if score > best["score"]:
            best = {
                "solution": solution,
                "score": score,
                "experts": experts,
                "critique": critique,
                "contributions": contributions,
            }
        if score >= quality_bar:
            break
        # EVALUATE → feedback se team RE-COMPOSE (AgentVerse ka core loop)
        fb = "; ".join(critique.get("fixes", []) or critique.get("weak", []))
        feedback = (feedback + " | " + fb)[:800] if feedback else fb
        if fb:
            _remember(goal, fb, score)
    summary, _ = await _llm(
        "Tum Manager ho. Final solution + score ko 3-4 line Hinglish summary + clear next-action me sameto. Sirf text.",
        f"Goal: {goal}\nSolution: {best['solution'][:1400]}\nScore: {best['score']}",
        max_tokens=220,
        temperature=0.4,
    )
    _log("manager", "agentverse_done", f"score={best['score']} rounds={len(rounds)}")
    out = {
        "ok": True,
        "run_id": run_id,
        "goal": goal,
        "pattern": "agentverse",
        "execute": execute,
        "rounds": rounds,
        "final_score": best["score"],
        "experts": [
            {"role": e["role"], "expertise": e.get("expertise", ""), "staff": e.get("staff", "")}
            for e in best["experts"]
        ],
        "contributions": best.get("contributions", []),
        "solution": best["solution"] or "(solution abhi nahi bana)",
        "critique": best["critique"],
        "summary": summary or "(summary abhi nahi bana)",
        "memory_used": len(recalled),
        "at": _now(),
    }
    _persist(out)
    return out


# --------------------------------------------------------------------------- #
# ENGINEERING crew (MetaGPT / OpenHands-inspired): Architect → Engineer → Reviewer
# → Tester. GOAL-driven feature/design aid. DRAFT-ONLY — code KABHI auto-apply nahi
# (code_upgrader ki philosophy: core code admin-approve pe hi badle). Yeh code_upgrader
# (signal→patch) ka complement = goal→design+plan+tests. Free-stack, never raises.
# --------------------------------------------------------------------------- #
async def coordinate_engineering(goal: str, context: str = "") -> dict:
    """4-role SDE crew → design + implementation plan + review + test plan (DRAFT)."""
    goal = (goal or "").strip()
    if len(goal) < 3:
        return {"ok": False, "error": "goal bahut chhota hai"}
    run_id = uuid.uuid4().hex[:12]
    _log("manager", "engineering_start", goal[:120])
    ctx = (context or "")[:1200]
    architect, _ = await _llm(
        "Tum Senior Software ARCHITECT ho (FastAPI/async/free-stack production system). Goal ke liye "
        "concise DESIGN do: components, data-flow, API/contract shape, key trade-offs. 6-10 line "
        "Hinglish. Sirf design.",
        f"Goal: {goal}\nContext: {ctx}",
        max_tokens=440,
        temperature=0.4,
    )
    implementer, _ = await _llm(
        "Tum ENGINEER ho. Architect ke design pe step-by-step IMPLEMENTATION PLAN do (files/functions, "
        "pseudo-code level — ACTUAL code apply mat karo). 6-10 line Hinglish. Sirf plan.",
        f"Goal: {goal}\nDesign: {architect[:1200]}",
        max_tokens=460,
        temperature=0.4,
    )
    reviewer, _ = await _llm(
        "Tum staff REVIEWER ho (security + reliability lens). Plan ke risks, edge-cases, failure-modes, "
        "security/idempotency/never-raise concerns + fixes list karo. 5-8 line Hinglish. Sirf review.",
        f"Goal: {goal}\nDesign: {architect[:800]}\nPlan: {implementer[:1000]}",
        max_tokens=380,
        temperature=0.3,
    )
    tester, _ = await _llm(
        "Tum QA ENGINEER ho. Is feature ke liye TEST PLAN do: unit + integration + failure-mode cases "
        "(kya assert karna). 5-8 line Hinglish. Sirf test plan.",
        f"Goal: {goal}\nPlan: {implementer[:1000]}\nReview: {reviewer[:600]}",
        max_tokens=360,
        temperature=0.3,
    )
    _log("manager", "engineering_done", goal[:120])
    out = {
        "ok": True,
        "run_id": run_id,
        "goal": goal,
        "pattern": "engineering_crew",
        "roles": ["architect", "engineer", "reviewer", "tester"],
        "design": architect or "(design pending)",
        "implementation_plan": implementer or "(plan pending)",
        "review": reviewer or "(review pending)",
        "test_plan": tester or "(tests pending)",
        "note": "DRAFT only — code auto-apply NAHI hua. Changes sirf code_upgrader/admin-approve se.",
        "at": _now(),
    }
    _persist(out)
    return out


async def council(question: str) -> dict:
    """Karpathy LLM Council — cross-model opinions → anonymized peer rank → Chairman synthesis."""
    from app.agents import llm_council

    question = (question or "").strip()
    if len(question) < 3:
        return {"ok": False, "error": "question bahut chhota hai"}
    run_id = uuid.uuid4().hex[:12]
    _log("manager", "council_start", question[:100])
    result = await llm_council.run_full_council(question)
    stage3 = result.get("stage3") or {}
    summary = stage3.get("response") or ""
    out: dict[str, Any] = {
        "run_id": run_id,
        "question": question,
        "pattern": "llm_council",
        "summary": summary,
        "at": _now(),
        **result,
    }
    if result.get("ok"):
        _log("manager", "council_done", summary[:80] if summary else "done")
        _persist(out)
    return out


__all__ = [
    "roster",
    "plan",
    "coordinate",
    "coordinate_advanced",
    "coordinate_hierarchical",
    "coordinate_agentverse",
    "coordinate_engineering",
    "fan_out",
    "debate",
    "council",
    "recent_runs",
    "memory_log",
]
