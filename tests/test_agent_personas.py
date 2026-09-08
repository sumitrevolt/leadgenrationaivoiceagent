"""ADR-184: Enterprise Sales-Force Persona Registry — contract tests.

Har staff agent ka DISTINCT enterprise persona hona chahiye:
  - unique system_prompt (word-for-word different)
  - sales-focused (sales_motivation field)
  - coordination_role defined
  - persona integrates into voice path + admin API

Run:  .venv/Scripts/python.exe -m pytest tests/test_agent_personas.py -q
"""

from __future__ import annotations

from app.platform.agent_personas import STAFF_PERSONAS, build_staff_system_prompt


# ------------------------------------------------------------------ existence
def test_registry_has_31_personas():
    """31 staff members = 31 distinct personas."""
    assert len(STAFF_PERSONAS) == 31


def test_every_persona_has_required_keys():
    required = {
        "name",
        "title",
        "tone",
        "expertise",
        "sales_motivation",
        "coordination_role",
        "system_prompt",
    }
    for staff_id, persona in STAFF_PERSONAS.items():
        missing = required - set(persona.keys())
        assert not missing, f"{staff_id} missing keys: {missing}"


# ------------------------------------------------------------------ uniqueness
def test_all_system_prompts_are_unique():
    prompts = [p["system_prompt"] for p in STAFF_PERSONAS.values()]
    assert len(set(prompts)) == len(prompts), "Duplicate system_prompt found!"


def test_all_titles_are_unique():
    titles = [p["title"] for p in STAFF_PERSONAS.values()]
    assert len(set(titles)) == len(titles), "Duplicate titles!"


def test_all_names_are_unique():
    names = [p["name"] for p in STAFF_PERSONAS.values()]
    assert len(set(names)) == len(names), "Duplicate names!"


def test_all_tones_are_unique():
    tones = [p["tone"] for p in STAFF_PERSONAS.values()]
    assert len(set(tones)) == len(tones), "Duplicate tones!"


def test_all_coordination_roles_unique():
    roles = [p["coordination_role"] for p in STAFF_PERSONAS.values()]
    assert len(set(roles)) == len(roles), "Duplicate coordination_roles!"


# ------------------------------------------------------------------ sales focus
def test_every_persona_mentions_sales():
    for staff_id, persona in STAFF_PERSONAS.items():
        prompt = persona["system_prompt"].lower()
        assert (
            "sale" in prompt
            or "revenue" in prompt
            or "close" in prompt
            or "lead" in prompt
            or "customer" in prompt
        ), f"{staff_id} persona has no sales focus"


def test_every_persona_has_sales_motivation():
    for staff_id, persona in STAFF_PERSONAS.items():
        motivation = persona.get("sales_motivation", "")
        assert len(motivation) > 10, f"{staff_id} sales_motivation too short"


# ------------------------------------------------------------------ key agents
def test_swara_is_senior_telecaller():
    p = STAFF_PERSONAS["swara"]
    assert "telecall" in p["system_prompt"].lower() or "call" in p["title"].lower()


def test_riya_is_lead_specialist():
    p = STAFF_PERSONAS["riya"]
    assert "lead" in p["system_prompt"].lower() or "discover" in p["title"].lower()


def test_manager_is_revenue_focused():
    p = STAFF_PERSONAS["manager"]
    assert "revenue" in p["system_prompt"].lower() or "revenue" in p["title"].lower()


# ------------------------------------------------------------------ prompt builder
def test_build_prompt_injects_client_and_niche():
    prompt = build_staff_system_prompt("swara", client_name="Jiya Makeover", niche="beauty")
    assert "Jiya Makeover" in prompt
    assert "beauty" in prompt.lower() or "beauty" in prompt


def test_build_prompt_returns_none_for_unknown_agent():
    result = build_staff_system_prompt("nonexistent_agent", client_name="Test", niche="test")
    assert result is None


def test_build_prompt_includes_sales_directive():
    prompt = build_staff_system_prompt("dev", client_name="Acme", niche="saas")
    assert prompt is not None
    assert "SALES GOAL" in prompt or "LeadGen" in prompt


# ------------------------------------------------------------------ team integration
def test_get_staff_persona_prompt_returns_string():
    from app.platform.team import get_staff_persona_prompt

    prompt = get_staff_persona_prompt("swara", client_name="Test Co", niche="beauty")
    assert isinstance(prompt, str)
    assert len(prompt) > 200


def test_staff_personas_summary_returns_list():
    from app.platform.team import staff_personas_summary

    summaries = staff_personas_summary()
    assert isinstance(summaries, list)
    assert len(summaries) == 31
    # Each summary must have id + display fields
    for s in summaries:
        assert "id" in s
        assert "name" in s
        assert "title" in s


# ------------------------------------------------------------------ coordination
def test_coordination_roles_cover_pipeline():
    """Team covers the full sales coordination pipeline."""
    roles = {p["coordination_role"].lower() for p in STAFF_PERSONAS.values()}
    # At least these pipeline stages must be present
    pipeline_keywords = [
        "prospect",
        "qualif",
        "call",
        "close",
        "onboard",
        "support",
        "content",
        "analytics",
    ]
    found = [kw for kw in pipeline_keywords if any(kw in r for r in roles)]
    assert len(found) >= 5, f"Pipeline coverage too thin: {found}"
