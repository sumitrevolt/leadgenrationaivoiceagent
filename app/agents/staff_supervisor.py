"""Scalable multi-agent orchestration via **langgraph-supervisor** (optional, opt-in).

Builds one hierarchical supervisor over the whole company STAFF roster
(``app/platform/team.py``) so the platform can coordinate MANY agents through a
single graph — the LangChain-official *supervisor* pattern (production-proven at
Uber/Klarna/LinkedIn). It reads ``STAFF`` dynamically, so adding a new staff
member automatically adds an agent — no rewiring.

Why additive + opt-in: the existing rule-based ``app/agents/supervisor.py`` and the
scheduled ``team_scheduler`` keep running unchanged. This module is NOT imported by
the app at startup; nothing happens until you enable it. Every path is defensive —
missing package / LLM key / any error returns a graceful dict, never raises.

Enable:
  pip install langgraph-supervisor langchain-openai
  export USE_LANGGRAPH_SUPERVISOR=1
  # plus a free OpenAI-compatible provider key already used by free_ai.py:
  #   CEREBRAS_API_KEY (preferred) or GROQ_API_KEY

Use (after enabling), e.g. wire into app/agents API:
  from app.agents.staff_supervisor import get_staff_supervisor
  result = get_staff_supervisor().run("Aaj ke naye inquiries ko qualify karke follow-up plan banao")
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _provider() -> tuple | None:
    """(base_url, api_key, model) for a free OpenAI-compatible provider, or None."""
    cb = os.getenv("CEREBRAS_API_KEY")
    if cb:
        return "https://api.cerebras.ai/v1", cb, os.getenv("DEFAULT_LLM", "gpt-oss-120b")
    gq = os.getenv("GROQ_API_KEY")
    if gq:
        return (
            "https://api.groq.com/openai/v1",
            gq,
            os.getenv("STRUCTURED_GROQ_MODEL", "openai/gpt-oss-120b"),
        )
    return None


class StaffSupervisor:
    """Lazy, defensive wrapper around a langgraph-supervisor graph over STAFF."""

    def __init__(self) -> None:
        self._enabled = _flag("USE_LANGGRAPH_SUPERVISOR")
        self._loaded = False
        self._broken = False
        self._graph = None

    def _build(self):
        if not self._enabled or self._broken:
            return None
        if self._loaded:
            return self._graph
        self._loaded = True
        try:
            from langchain_openai import ChatOpenAI
            from langgraph.prebuilt import create_react_agent
            from langgraph_supervisor import create_supervisor

            from app.platform.team import STAFF

            prov = _provider()
            if not prov:
                raise RuntimeError("no provider key (set CEREBRAS_API_KEY or GROQ_API_KEY)")
            base_url, api_key, model_name = prov
            model = ChatOpenAI(
                model=model_name, base_url=base_url, api_key=api_key, temperature=0.3
            )

            agents = []
            for key, info in STAFF.items():
                role = info.get("role", key)
                duties = info.get("duties") or info.get("duty") or ""
                if isinstance(duties, list | tuple):
                    duties = ", ".join(map(str, duties))
                name = info.get("name", key)
                prompt = (
                    f"You are {name}, the {role} at LeadGen AI (AI marketing + AI voice agent "
                    f"for Indian small businesses). Your duties: {duties}. Only handle tasks that "
                    f"fit your role; otherwise say so briefly. Reply concisely in Hinglish (Roman script)."
                )
                agents.append(create_react_agent(model=model, tools=[], name=key, prompt=prompt))

            supervisor_prompt = (
                "You are the Manager (Boss) of LeadGen AI's AI staff. Read the task, route it to "
                "the right specialist agent(s) by name, and coordinate multiple agents when a task "
                "needs more than one. Be decisive and concise. Final answer in Hinglish."
            )
            self._graph = create_supervisor(agents, model=model, prompt=supervisor_prompt).compile()
            logger.info("StaffSupervisor: graph built over %d agents", len(agents))
            return self._graph
        except Exception as exc:  # package/key/API drift -> disable, never crash
            self._broken = True
            self._graph = None
            logger.info("StaffSupervisor disabled (%s)", exc)
            return None

    @property
    def active(self) -> bool:
        return self._build() is not None

    def run(self, task: str) -> dict:
        """Route `task` through the supervisor. Always returns a dict, never raises."""
        g = self._build()
        if g is None:
            return {
                "ok": False,
                "task": task,
                "reason": "supervisor unavailable — pip install langgraph-supervisor langchain-openai, "
                "set USE_LANGGRAPH_SUPERVISOR=1 and a provider key (CEREBRAS_API_KEY/GROQ_API_KEY)",
            }
        try:
            out = g.invoke({"messages": [{"role": "user", "content": task}]})
            msgs = out.get("messages", []) if isinstance(out, dict) else []
            final = ""
            if msgs:
                last = msgs[-1]
                final = getattr(last, "content", None)
                if final is None and isinstance(last, dict):
                    final = last.get("content", "")
            # Harness supervisor-family shadow (record-only; INERT unless flags +
            # the routed agent is in canary agents + supervisor loop allowlisted).
            # delegated agent is derived from the graph's own message metadata —
            # never guessed from prose. NEVER re-runs the graph; never raises.
            try:
                from app.agents.harness.adapters import observe_supervisor_action

                # Structured selection: the routed WORKER is the message authored by
                # a STAFF agent (name in STAFF), not the final supervisor message.
                # This is the graph's own structured metadata, never guessed prose.
                try:
                    from app.platform.team import STAFF

                    _staff_keys = {str(k).strip().lower() for k in (STAFF or {}).keys()}
                except Exception:
                    _staff_keys = set()

                def _mname(m):
                    n = getattr(m, "name", None)
                    if n is None and isinstance(m, dict):
                        n = m.get("name")
                    return str(n).strip().lower() if n else None

                _deleg = None
                _sel = "UNKNOWN"
                for _m in reversed(msgs):
                    _nm = _mname(_m)
                    if _nm and _nm in _staff_keys and _nm != "supervisor":
                        _deleg, _sel = _nm, "MESSAGE_NAME"
                        break
                if _deleg is None and msgs:  # fall back to last name (provenance UNKNOWN)
                    _deleg = _mname(msgs[-1])
                _gid = f"staff_supervisor:{abs(hash(task)) % 10**8}"  # per-run id (avoids cross-run dedup collision)
                observe_supervisor_action(
                    supervisor_run_id=_gid,
                    graph_run_id=_gid,
                    graph_step=len(msgs),
                    tool_call_id=None,
                    supervisor_implementation="staff_supervisor",
                    actor_id="manager",
                    delegated_agent_id=_deleg,
                    tenant_id="",
                    tool_name=(_deleg or ""),
                    tool_arguments={"task": task},
                    actual_executor="staff_supervisor.graph",
                    actual_result={"turns": len(msgs)},
                    latency_ms=0.0,
                    graph_metadata={
                        "selection_source": _sel,
                        "actual_node": "staff_supervisor.graph",
                    },
                )
            except Exception:
                pass
            return {"ok": True, "task": task, "reply": final or "", "turns": len(msgs)}
        except Exception as exc:
            logger.info("StaffSupervisor.run error: %s", exc)
            return {"ok": False, "task": task, "reason": f"run error: {exc}"}


_singleton: StaffSupervisor | None = None


def get_staff_supervisor() -> StaffSupervisor:
    """Process-wide StaffSupervisor (lazy singleton)."""
    global _singleton
    if _singleton is None:
        _singleton = StaffSupervisor()
    return _singleton


def high_stakes_enabled() -> bool:
    return _flag("USE_LANGGRAPH_SUPERVISOR") and _flag("USE_LANGGRAPH_HIGH_STAKES")


def run_high_stakes(task: str) -> dict[str, Any]:
    """LangGraph supervisor for sales/process breakpoints. Never raises."""
    if not high_stakes_enabled():
        return {
            "ok": False,
            "reason": "USE_LANGGRAPH_HIGH_STAKES=1 + USE_LANGGRAPH_SUPERVISOR=1 required",
        }
    try:
        return get_staff_supervisor().run(task)
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:200]}


__all__ = ["StaffSupervisor", "get_staff_supervisor", "high_stakes_enabled", "run_high_stakes"]
