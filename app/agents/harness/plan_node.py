"""MetaGPT-ActionNode-style structured plan fill/review/revise for coordinator.plan().

Steal-item #1 from the MetaGPT evaluation (2026-08-05). Instead of scraping
freeform JSON out of LLM prose (`coordinator._extract_list`) and silently
dropping to a hardcoded chain when the model returns junk, we run the ActionNode
cycle over a typed output schema:

    compile  -> caller builds strict system/user prompts (kept in coordinator)
    fill     -> first LLM call
    review   -> validate against the pydantic schema; on failure build a review
                prompt carrying the concrete validation error + bad output
    revise   -> bounded regeneration with the review feedback
    adopt    -> valid plan wins; else return None so the caller falls back to
                legacy `_extract_list` + its hardcoded chain

INERT by default: this module never runs unless a caller arms it. The single
canary caller is `coordinator.plan()` under the COORD_PLAN_NODE flag; the legacy
parse path stays authoritative as the fallback.

No app.* imports at module top and no default LLM surface — `llm_fn` is injected
so this module stays importable in isolation (same invariant as contracts.py) and
can never create a second un-capped LLM path. The injected function MUST honour
the coordinator `_llm` signature:
    async def llm_fn(system: str, user: str, max_tokens: int, temperature: float) -> tuple[str, str]
Never raises.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional, Union

from pydantic import BaseModel, Field

_LLM_RETURN = tuple[str, str]
LLMFn = Callable[..., Awaitable[_LLM_RETURN]]

_MAX_TASK = 240  # matches coordinator.plan task cap
_MAX_STEPS = 12  # hard upper bound before validation rejects

_SOURCE_STRUCTURED = "STRUCTURED_NATIVE"
_SOURCE_REVIEWED = "STRUCTURED_REVIEWED"

_FENCE_MARKERS = ("```json", "```", "JSON:", "json:")


class PlanItem(BaseModel):
    """One delegation step — the minimal typed schema the fill step must match."""

    model_config = {"extra": "forbid"}

    agent: str
    task: str


class PlanFill(BaseModel):
    """Runtime-generated output schema (ActionNode-style). A bare list also parses."""

    plan: list[PlanItem] = Field(default_factory=list)


def _extract_json(text: str) -> Any:
    """Salvage a JSON value from possibly-noisy model output. None if unfindable."""
    t = (text or "").strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        pass
    # Strip markdown fences / explicit JSON markers first.
    for marker in _FENCE_MARKERS:
        if marker in t:
            t = t.split(marker, 1)[1]
            if "```" in t:
                t = t.rsplit("```", 1)[0]
            break
    t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # Last resort: pull the first balanced list/object out of surrounding prose.
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        i, j = t.find(open_ch), t.rfind(close_ch)
        if i != -1 and j > i:
            try:
                return json.loads(t[i : j + 1])
            except Exception:
                continue
    return None


def parse_plan(
    raw: str, allowed_agents: Union[set[str], list[str]]
) -> tuple[list[dict] | None, str]:
    """Validate raw LLM output into ``[{agent, task}]`` steps.

    Returns ``(steps, "")`` on success or ``(None, reason)`` on failure. Strict on
    purpose — a single invalid item triggers the review/revise round instead of
    being silently salvaged.
    """
    allowed = set(allowed_agents or [])
    data = _extract_json(raw)
    if data is None:
        return None, "no JSON found in model output"
    if isinstance(data, dict) and isinstance(data.get("plan"), list):
        data = data["plan"]
    if not isinstance(data, list):
        return None, "top-level value is not a list"
    if not data:
        return None, "empty plan"
    steps: list[dict] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return None, f"item {i} is not an object"
        agent = str(item.get("agent") or "").strip()
        task = str(item.get("task") or "").strip()
        if not agent:
            return None, f"item {i} missing agent"
        if agent not in allowed:
            return None, f"item {i}: agent '{agent}' not in allowed roster"
        if not task:
            return None, f"item {i} missing task"
        steps.append({"agent": agent, "task": task[:_MAX_TASK]})
        if len(steps) > _MAX_STEPS:
            return None, f"plan exceeds {_MAX_STEPS} steps"
    return steps, ""


def _snippet(raw: str, limit: int = 400) -> str:
    return (raw or "")[:limit]


async def _safe_llm(
    llm_fn: LLMFn, system: str, user: str, max_tokens: int, temperature: float
) -> tuple[str, str]:
    """Defensive wrapper — a provider exception must never escape."""
    try:
        out, prov = await llm_fn(system, user, max_tokens=max_tokens, temperature=temperature)
        return (out or "").strip(), prov
    except Exception:
        return "", "none"


def _review_system(allowed: set[str]) -> str:
    return (
        "Tum ek strict PLAN REVIEWER ho. Diya gaya JSON plan SCHEMA se mismatch karta hai. "
        'Output ya to JSON array ho: [{"agent":"<STAFF key>","task":"<Hinglish task>"}] '
        'ya object: {"plan":[... isi shape ka array ...]}. '
        f"agent ALLOWED keys (sirf yeh): {', '.join(sorted(allowed))}. "
        "Har item me agent + task DONO chahiye. "
        "Errors fix karke SIRF poora corrected JSON array lautao — kuch aur mat likho."
    )


async def structured_plan(
    *,
    goal: str,
    system: str,
    user: str,
    allowed_agents: Union[set[str], list[str]],
    llm_fn: LLMFn | None,
    max_review_rounds: int = 1,
    max_steps: int = 5,
) -> dict | None:
    """ActionNode-style fill -> review -> revise over a typed plan schema.

    Returns ``{"steps": [{agent, task}, ...], "source": str, "reviews": int}`` on
    success, or ``None`` so the caller can fall back to its legacy parse path.
    ``max_steps`` trims (never rejects) the adopted plan.
    """
    if llm_fn is None:
        return None
    allowed = set(allowed_agents or [])
    rounds = max(0, int(max_review_rounds or 0))

    # FILL — first attempt (same budget/temperature as the legacy plan call).
    raw, _ = await _safe_llm(llm_fn, system, user, max_tokens=300, temperature=0.2)
    steps, err = parse_plan(raw, allowed)
    if steps is not None:
        return {"steps": steps[:max_steps], "source": _SOURCE_STRUCTURED, "reviews": 0}

    # REVIEW + REVISE — bounded self-correction against the schema.
    review_sys = _review_system(allowed)
    reviews = 0
    for _ in range(rounds):
        review_user = (
            f"Goal: {goal}\n"
            f"Validation error: {err}\n"
            f"Aapka pichhla output (galat):\n{_snippet(raw)}\n"
            "Corrected JSON array do."
        )
        raw2, _ = await _safe_llm(llm_fn, review_sys, review_user, max_tokens=300, temperature=0.2)
        reviews += 1
        steps, err = parse_plan(raw2, allowed)
        if steps is not None:
            return {"steps": steps[:max_steps], "source": _SOURCE_REVIEWED, "reviews": reviews}
        raw = raw2

    return None


__all__ = [
    "LLMFn",
    "PlanFill",
    "PlanItem",
    "parse_plan",
    "structured_plan",
]
