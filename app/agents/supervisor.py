"""
LangGraph Supervisor — minimal multi-agent orchestration (P2 of stack roadmap).

Graph (3 nodes):

    START -> supervisor -> {data_agent | leads_agent} -> END

  - supervisor   : rule-based router (NO LLM call) — task keywords decide route.
  - data_agent   : KB-grounded answer/plan (client namespace -> niche fallback),
                   mirrors the provisioned role="data" agent.
  - leads_agent  : concrete outreach/qualification plan from NICHES config,
                   mirrors the provisioned role="leads" agent.

Degrades gracefully: if `langgraph` is not installed, AGENTS_AVAILABLE=False and
run_supervisor_task() raises RuntimeError — API layer turns that into HTTP 501.
Persistence: SQLite checkpointer at data/agent_graph.db (best-effort).
"""

import os
from typing import Any, TypedDict

from app.niches import NICHES
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Node names exposed for /agents/status (defined even without langgraph).
GRAPH_NODES: list[str] = ["supervisor", "data_agent", "leads_agent"]

_DB_PATH = os.path.join("data", "agent_graph.db")

# Rule-based routing keywords (substring match on the lowercased task).
_DATA_KEYWORDS = ("kb", "seed", "enrich", "research", "profile")
_LEADS_KEYWORDS = ("lead", "call", "qualify", "campaign", "outreach")

# --------------------------------------------------------------------------- #
# Optional dependency: langgraph (ALL langgraph imports guarded here)
# --------------------------------------------------------------------------- #
try:
    from langgraph.graph import END, START, StateGraph

    AGENTS_AVAILABLE = True
except Exception as _e:  # pragma: no cover - depends on environment
    AGENTS_AVAILABLE = False
    logger.info(f"langgraph not installed — agents engine disabled ({_e})")

# Checkpointers (separate optional package: langgraph-checkpoint-sqlite).
_ASYNC_SAVER_CLS = None
_SYNC_SAVER_CLS = None
if AGENTS_AVAILABLE:
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as _ASYNC_SAVER_CLS
    except Exception:
        _ASYNC_SAVER_CLS = None
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver as _SYNC_SAVER_CLS
    except Exception:
        _SYNC_SAVER_CLS = None
    if _ASYNC_SAVER_CLS is None and _SYNC_SAVER_CLS is None:
        logger.info("langgraph sqlite checkpointer unavailable — running without persistence")


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
class AgentState(TypedDict, total=False):
    messages: list
    client_id: str | None
    niche: str
    task: str
    result: str | None
    route: str | None


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def route_for_task(task: str) -> str:
    """
    Pure rule-based router — NO LLM call, NO langgraph dependency.

    Data keywords pehle check hote hain, phir leads keywords; kuch match na ho
    to default "leads_agent". Substring match on the lowercased task —
    behavior exactly the same as the original inline supervisor logic.
    """
    task = (task or "").lower()
    if any(k in task for k in _DATA_KEYWORDS):
        return "data_agent"
    if any(k in task for k in _LEADS_KEYWORDS):
        return "leads_agent"
    return "leads_agent"  # default


# Lightweight FREE-LLM router prompt — classify a task into exactly one agent.
_ROUTER_SYSTEM = (
    "You route a task to ONE agent for an Indian lead-gen + data platform. Labels:\n"
    "- data_agent: needs knowledge-base research, business details/profiles, or data metrics.\n"
    "- leads_agent: needs calling, campaigns, lead qualification, or sales pitches.\n"
    "Reply with ONLY one word: data_agent or leads_agent."
)


async def semantic_route_for_task(task: str) -> str:
    """Async semantic router via the FREE LLM (Cerebras/Groq chain through free_ai).

    `route_for_task()` keyword matching = zero-latency fallback: langgraph na ho,
    LLM fail ho, ya output unexpected ho to seedha keyword router. Never raises,
    koi paid service nahi (free_ai chain).
    """
    task = (task or "").strip()
    if not task:
        return "leads_agent"
    if not AGENTS_AVAILABLE:
        return route_for_task(task)
    try:
        from app.voice_agent.free_ai import chat

        reply, _ = await chat(
            _ROUTER_SYSTEM,
            [{"role": "user", "content": task[:500]}],
            max_tokens=6,
            temperature=0.0,
        )
        low = (reply or "").strip().lower()
        if "data_agent" in low:
            return "data_agent"
        if "leads_agent" in low:
            return "leads_agent"
        if "data" in low and "lead" not in low:
            return "data_agent"
        if "lead" in low and "data" not in low:
            return "leads_agent"
    except Exception as e:
        logger.debug(f"semantic router LLM failed ({e}); keyword fallback.")
    return route_for_task(task)


async def supervisor_node(state: AgentState) -> dict[str, Any]:
    """Semantic FREE-LLM router (keyword fallback). Sets state['route']."""
    route = await semantic_route_for_task(state.get("task") or "")
    logger.debug(f"supervisor routed task to {route}")
    return {"route": route}


def _llm_brain():
    """Lazy import — keeps this module importable even if voice deps misbehave."""
    from app.voice_agent.llm_brain import LLMBrain

    return LLMBrain()


async def data_agent_node(state: AgentState) -> dict[str, Any]:
    """KB-grounded answer/plan for the client (role='data' agent equivalent)."""
    task = state.get("task") or ""
    client_id = state.get("client_id")
    niche = state.get("niche") or "general"

    # Retrieve top 3 chunks: client namespace first, niche namespace fallback.
    chunks: list[str] = []
    try:
        from app.voice_agent.kb_loader import bootstrap_default_kb

        kb = bootstrap_default_kb()
        hits: list[dict[str, Any]] = []
        if client_id:
            hits = kb.retrieve(task, k=3, namespace=f"client:{client_id}")
        if not hits:
            hits = kb.retrieve(task, k=3, namespace=niche)
        chunks = [h.get("text", "") for h in (hits or []) if h.get("text")]
    except Exception as e:  # pragma: no cover - KB is best-effort
        logger.warning(f"data_agent KB retrieval failed: {e}")

    context = "\n".join(f"- {c}" for c in chunks) or "(no knowledge-base context found)"
    cfg = NICHES.get(niche, {})
    prompt = (
        f"[DATA AGENT TASK] {task}\n\n"
        f"Knowledge base context (top matches):\n{context}\n\n"
        "Ground your answer in the context above. Produce a concise, actionable "
        "answer or plan for this task (short bullet points where useful)."
    )
    brain = _llm_brain()
    result = await brain.generate_response(
        conversation_history=[{"role": "user", "content": prompt}],
        niche=niche,
        client_name=f"Client {client_id}" if client_id else "Platform",
        client_service=cfg.get("name", niche),
    )
    messages = list(state.get("messages") or [])
    messages.append({"role": "assistant", "content": result, "agent": "data_agent"})
    return {"result": result, "messages": messages}


async def leads_agent_node(state: AgentState) -> dict[str, Any]:
    """Calling/qualification plan from niche config (role='leads' agent equivalent)."""
    task = state.get("task") or ""
    client_id = state.get("client_id")
    niche = state.get("niche") or "general"
    cfg = NICHES.get(niche, {})

    questions = cfg.get("qualification_questions", []) or []
    q_block = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions)) or "(none configured)"
    prompt = (
        f"[LEADS AGENT TASK] {task}\n\n"
        f"Niche: {cfg.get('name', niche)} (target audience: {cfg.get('target_type', 'b2c')})\n"
        f"Pitch hook: {cfg.get('pitch_hook') or '(none configured)'}\n"
        f"Qualification questions:\n{q_block}\n\n"
        "Give a concrete outreach/qualification response for this task: what to "
        "say on the call, which qualification questions to ask in what order, "
        "and the next step to book (appointment/callback)."
    )
    brain = _llm_brain()
    result = await brain.generate_response(
        conversation_history=[{"role": "user", "content": prompt}],
        niche=niche,
        client_name=f"Client {client_id}" if client_id else "Platform",
        client_service=cfg.get("name", niche),
    )
    messages = list(state.get("messages") or [])
    messages.append({"role": "assistant", "content": result, "agent": "leads_agent"})
    return {"result": result, "messages": messages}


# --------------------------------------------------------------------------- #
# Graph wiring (built once; compiled per run so the checkpointer can attach)
# --------------------------------------------------------------------------- #
_WORKFLOW = None
if AGENTS_AVAILABLE:
    _WORKFLOW = StateGraph(AgentState)
    _WORKFLOW.add_node("supervisor", supervisor_node)
    _WORKFLOW.add_node("data_agent", data_agent_node)
    _WORKFLOW.add_node("leads_agent", leads_agent_node)
    _WORKFLOW.add_edge(START, "supervisor")
    _WORKFLOW.add_conditional_edges(
        "supervisor",
        lambda s: s.get("route") or "leads_agent",
        {"data_agent": "data_agent", "leads_agent": "leads_agent"},
    )
    _WORKFLOW.add_edge("data_agent", END)
    _WORKFLOW.add_edge("leads_agent", END)


async def _execute(state: AgentState, config: dict[str, Any]) -> dict[str, Any]:
    """Run the graph with the best available checkpointer (best-effort)."""
    # 1) AsyncSqliteSaver — the correct saver for async nodes (.ainvoke).
    if _ASYNC_SAVER_CLS is not None:
        try:
            os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
            async with _ASYNC_SAVER_CLS.from_conn_string(_DB_PATH) as saver:
                graph = _WORKFLOW.compile(checkpointer=saver)
                return await graph.ainvoke(state, config=config)
        except Exception as e:
            logger.warning(f"async sqlite checkpointer failed ({e}); retrying without persistence")
    # 2) Sync SqliteSaver — works only if this langgraph version bridges async;
    #    NotImplementedError surfaces immediately (first checkpoint read).
    elif _SYNC_SAVER_CLS is not None:
        try:
            os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
            import sqlite3

            conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
            try:
                graph = _WORKFLOW.compile(checkpointer=_SYNC_SAVER_CLS(conn))
                return await graph.ainvoke(state, config=config)
            finally:
                conn.close()
        except NotImplementedError:
            logger.info(
                "sync SqliteSaver does not support async graphs; running without persistence"
            )
        except Exception as e:
            logger.warning(f"sqlite checkpointer failed ({e}); retrying without persistence")
    # 3) No persistence.
    graph = _WORKFLOW.compile()
    return await graph.ainvoke(state, config=config)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
async def run_supervisor_task(
    task: str,
    client_id: str | None = None,
    niche: str = "general",
) -> dict[str, Any]:
    """
    Route a task through the supervisor graph and return the agent's result.

    Returns: {"route": "data_agent"|"leads_agent", "result": str, "niche": str}
    Raises:  RuntimeError if langgraph is not installed.
    """
    if not AGENTS_AVAILABLE:
        raise RuntimeError("langgraph not installed")

    # Loose niche strings ("solar", "real estate") -> canonical NICHES key.
    try:
        from app.platform.agent_provisioner import resolve_niche_key

        niche_key = resolve_niche_key(niche)
    except Exception:
        niche_key = niche if niche in NICHES else "general"

    initial: AgentState = {
        "messages": [{"role": "user", "content": task}],
        "client_id": client_id,
        "niche": niche_key,
        "task": task,
        "result": None,
        "route": None,
    }
    thread_id = f"{client_id or 'platform'}:{task[:20]}"
    config = {"configurable": {"thread_id": thread_id}}

    import time as _time

    _t0 = _time.monotonic()
    out = await _execute(initial, config)
    # Harness supervisor-family shadow (record-only; INERT unless AGENT_HARNESS +
    # AGENT_HARNESS_SHADOW on, delegated worker in canary agents, supervisor in
    # canary loops). NEVER re-runs the graph/model/node; never raises.
    try:
        from app.agents.harness.adapters import observe_supervisor_action

        _route = out.get("route") or "leads_agent"
        _worker = "dev" if _route == "data_agent" else "rohan"
        observe_supervisor_action(
            supervisor_run_id=thread_id,
            graph_run_id=thread_id,
            graph_step=1,
            tool_call_id=None,
            supervisor_implementation="supervisor",
            actor_id="manager",
            delegated_agent_id=_worker,
            tenant_id=str(client_id or ""),
            tool_name=_route,
            tool_arguments={"task": task, "niche": niche_key},
            actual_executor=f"{_route}_node",
            actual_result={"route": _route, "result_len": len(str(out.get("result") or ""))},
            latency_ms=round((_time.monotonic() - _t0) * 1000, 1),
            graph_metadata={
                "selection_source": "GRAPH_ROUTE",
                "route_label": _route,
                "actual_node": f"{_route}_node",
            },
        )
    except Exception:
        pass
    try:  # Team activity: Manager ne task route kiya
        from app.platform.team import log_event

        route = out.get("route") or "?"
        worker = "dev" if route == "data_agent" else "rohan"
        log_event("manager", "task_routed", f"Task '{task[:60]}' → {route} ({niche_key})")
        log_event(
            worker,
            "task_done",
            f"{('KB/data kaam' if worker == 'dev' else 'Outreach plan')}: {task[:60]}",
        )
    except Exception:
        pass
    return {
        "route": out.get("route"),
        "result": out.get("result"),
        "niche": niche_key,
    }
