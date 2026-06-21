"""Voice agent roles — booking + receptionist personas."""

from __future__ import annotations


def test_voice_roles_normalize():
    from app.voice_agent.voice_roles import normalize_role

    assert normalize_role("telecaller") == "telecaller"
    assert normalize_role("booking") == "booking_agent"
    assert normalize_role("appointment") == "booking_agent"
    assert normalize_role("reception") == "receptionist"
    assert normalize_role("inbound") == "receptionist"
    assert normalize_role(None) == "telecaller"
    assert normalize_role("unknown_xyz") == "telecaller"


def test_voice_agents_catalog():
    from app.voice_agent.voice_roles import list_voice_agents, staff_for_role

    agents = list_voice_agents()
    ids = {a["role"] for a in agents}
    assert ids == {"telecaller", "booking_agent", "receptionist"}
    assert staff_for_role("booking") == "ananya"
    assert staff_for_role("receptionist") == "riya"
    assert staff_for_role("qualify") == "swara"


def test_telecaller_brain_booking_role_prompt():
    from app.voice_agent.telecaller_brain import TelecallerBrain

    brain = TelecallerBrain(
        niche="hospital_appointments",
        client_name="City Clinic",
        voice_role="booking_agent",
    )
    assert brain.voice_role == "booking_agent"
    assert "Ananya" in brain.system_prompt
    assert "appointment" in brain.system_prompt.lower()
    opener = brain.opening_line()
    assert "Ananya" in opener
    assert "City Clinic" in opener


def test_telecaller_brain_receptionist_role():
    from app.voice_agent.telecaller_brain import TelecallerBrain

    brain = TelecallerBrain(
        niche="dental_implants",
        client_name="Smile Dental",
        voice_role="receptionist",
    )
    assert brain.voice_role == "receptionist"
    assert "Riya" in brain.system_prompt
    assert "reception" in brain.system_prompt.lower() or "madad" in brain.system_prompt.lower()
    opener = brain.opening_line()
    assert "Riya" in opener


def test_voice_product_agents_route():
    from app.api.voice_product import voice_agents
    import asyncio

    out = asyncio.run(voice_agents())
    assert out["count"] == 3
    assert len(out["agents"]) == 3
    names = {a["name"] for a in out["agents"]}
    assert names >= {"Swara", "Ananya", "Riya"}
