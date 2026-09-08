"""COORD_PLAN_NODE — MetaGPT-ActionNode-style structured plan fill/review/revise.

Steal-item #1 from the MetaGPT evaluation (2026-08-05). Covers the pure
parse/validate step, the fill -> review -> revise cycle (fake LLM), and the
INERT contract: flag OFF => coordinator.plan() behaviour is byte-identical to
legacy (plan_node never invoked); flag ON => plan_node is the canary with the
legacy `_extract_list` path retained as fallback.
"""

from __future__ import annotations

import asyncio

from app.agents.harness import plan_node

ALLOWED = {"dev", "rohan", "isha"}


# ---- pure parse/validate -------------------------------------------------- #
def test_parse_plan_accepts_bare_list():
    steps, err = plan_node.parse_plan('[{"agent":"dev","task":"research"}]', ALLOWED)
    assert err == ""
    assert steps == [{"agent": "dev", "task": "research"}]


def test_parse_plan_accepts_object_with_plan_key():
    steps, err = plan_node.parse_plan('{"plan":[{"agent":"isha","task":"post"}]}', ALLOWED)
    assert err == ""
    assert steps == [{"agent": "isha", "task": "post"}]


def test_parse_plan_strips_code_fences_and_prose():
    steps, err = plan_node.parse_plan('```json\n[{"agent":"rohan","task":"call"}]\n```', ALLOWED)
    assert err == ""
    assert steps == [{"agent": "rohan", "task": "call"}]

    steps, err = plan_node.parse_plan('Here is the plan:\n[{"agent":"dev","task":"scan"}]', ALLOWED)
    assert err == ""
    assert steps == [{"agent": "dev", "task": "scan"}]


def test_parse_plan_rejects_unknown_agent():
    steps, err = plan_node.parse_plan('[{"agent":"hacker","task":"x"}]', ALLOWED)
    assert steps is None
    assert "not in allowed roster" in err


def test_parse_plan_rejects_bad_shapes():
    assert plan_node.parse_plan("[{}]", ALLOWED)[0] is None
    assert plan_node.parse_plan('[{"agent":"dev"}]', ALLOWED)[0] is None
    assert plan_node.parse_plan('[{"task":"x"}]', ALLOWED)[0] is None
    assert plan_node.parse_plan("not json at all", ALLOWED)[0] is None
    assert plan_node.parse_plan("[]", ALLOWED)[0] is None
    assert plan_node.parse_plan("", ALLOWED)[0] is None


def test_parse_plan_bounds_task_length():
    long = "x" * 999
    steps, err = plan_node.parse_plan(f'[{{"agent":"dev","task":"{long}"}}]', ALLOWED)
    assert err == ""
    assert len(steps[0]["task"]) == plan_node._MAX_TASK


# ---- fill -> review -> revise (fake LLM) ---------------------------------- #
def test_fill_valid_first_try_no_review():
    async def fake(system, user, **kw):
        return '[{"agent":"dev","task":"research"}]', "none"

    res = asyncio.run(
        plan_node.structured_plan(
            goal="g",
            system="s",
            user="u",
            allowed_agents=ALLOWED,
            llm_fn=fake,
            max_review_rounds=1,
        )
    )
    assert res is not None
    assert res["steps"] == [{"agent": "dev", "task": "research"}]
    assert res["source"] == plan_node._SOURCE_STRUCTURED
    assert res["reviews"] == 0


def test_review_revises_bad_plan_then_adopts():
    calls = {"n": 0}

    async def flaky(system, user, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return '[{"agent":"nope","task":"x"}]', "none"
        return '[{"agent":"dev","task":"research"}]', "none"

    res = asyncio.run(
        plan_node.structured_plan(
            goal="g",
            system="s",
            user="u",
            allowed_agents=ALLOWED,
            llm_fn=flaky,
            max_review_rounds=2,
        )
    )
    assert res is not None
    assert res["steps"] == [{"agent": "dev", "task": "research"}]
    assert res["source"] == plan_node._SOURCE_REVIEWED
    assert res["reviews"] == 1
    assert calls["n"] == 2


def test_all_fail_returns_none_for_legacy_fallback():
    async def bad(system, user, **kw):
        return "complete nonsense", "none"

    res = asyncio.run(
        plan_node.structured_plan(
            goal="g",
            system="s",
            user="u",
            allowed_agents=ALLOWED,
            llm_fn=bad,
            max_review_rounds=2,
        )
    )
    assert res is None


def test_llm_raising_never_crashes():
    async def boom(system, user, **kw):
        raise RuntimeError("provider down")

    res = asyncio.run(
        plan_node.structured_plan(
            goal="g",
            system="s",
            user="u",
            allowed_agents=ALLOWED,
            llm_fn=boom,
            max_review_rounds=1,
        )
    )
    assert res is None


def test_zero_review_rounds_skips_review():
    calls = {"n": 0}

    async def flaky(system, user, **kw):
        calls["n"] += 1
        return '[{"agent":"nope","task":"x"}]', "none"

    res = asyncio.run(
        plan_node.structured_plan(
            goal="g",
            system="s",
            user="u",
            allowed_agents=ALLOWED,
            llm_fn=flaky,
            max_review_rounds=0,
        )
    )
    assert res is None
    assert calls["n"] == 1  # only the fill call happened


def test_max_steps_trimmed():
    async def fake(system, user, **kw):
        return (
            '[{"agent":"dev","task":"a"},{"agent":"isha","task":"b"},{"agent":"rohan","task":"c"}]',
            "none",
        )

    res = asyncio.run(
        plan_node.structured_plan(
            goal="g",
            system="s",
            user="u",
            allowed_agents=ALLOWED,
            llm_fn=fake,
            max_review_rounds=0,
            max_steps=2,
        )
    )
    assert len(res["steps"]) == 2


def test_none_llm_fn_inert_safe():
    res = asyncio.run(
        plan_node.structured_plan(
            goal="g", system="s", user="u", allowed_agents=ALLOWED, llm_fn=None
        )
    )
    assert res is None
