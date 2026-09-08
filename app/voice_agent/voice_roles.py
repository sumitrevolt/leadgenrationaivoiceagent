"""
Voice agent roles — Product 2 ke alag personas (Swara telecaller ke alawa).

Roles:
  - telecaller   → Swara (default) — outbound qualify + pitch
  - booking_agent → Ananya — appointment / site-visit / demo BOOK (har niche)
  - receptionist  → Riya — inbound customer reception (route, message, book)

Consumers: TelecallerBrain, vobiz_stream, web_call, voice_product API, team.py STAFF.
Import-safe; kabhi raise nahi karta.
"""

from __future__ import annotations

from typing import Any

# Canonical role ids (API / customParameters / web-call `flow`)
VOICE_ROLES: dict[str, dict[str, Any]] = {
    "telecaller": {
        "id": "telecaller",
        "staff_id": "swara",
        "name": "Swara",
        "emoji": "📞",
        "title": "AI Telecaller",
        "product": "voice",
        "direction": "outbound",
        "goal": "Niche leads ko qualify karna, objections handle, appointment/demo book karna",
    },
    "booking_agent": {
        "id": "booking_agent",
        "staff_id": "ananya",
        "name": "Ananya",
        "emoji": "📅",
        "title": "AI Appointment Booker",
        "product": "voice",
        "direction": "outbound",
        "goal": "End-customers ke liye appointment, site-visit ya demo slot confirm karna (har niche)",
    },
    "receptionist": {
        "id": "receptionist",
        "staff_id": "riya",
        "name": "Riya",
        "emoji": "🛎️",
        "title": "AI Receptionist",
        "product": "voice",
        "direction": "inbound",
        "goal": "Customer calls answer karna — department route, message, appointment book",
    },
}

# Aliases from web-call / campaign `flow` param
_FLOW_ALIASES: dict[str, str] = {
    "qualify": "telecaller",
    "telecaller": "telecaller",
    "sales": "telecaller",
    "booking": "booking_agent",
    "appointment": "booking_agent",
    "book": "booking_agent",
    "reception": "receptionist",
    "receptionist": "receptionist",
    "inbound": "receptionist",
    "front_desk": "receptionist",
}


def normalize_role(raw: str | None) -> str:
    """Map flow/role string → canonical role id. Unknown → telecaller."""
    key = (raw or "telecaller").strip().lower().replace("-", "_")
    if key in VOICE_ROLES:
        return key
    return _FLOW_ALIASES.get(key, "telecaller")


def list_voice_agents() -> list[dict[str, Any]]:
    """Public catalog for /api/voice/agents."""
    out = []
    for role_id, meta in VOICE_ROLES.items():
        out.append(
            {
                "role": role_id,
                "staff_id": meta["staff_id"],
                "name": meta["name"],
                "emoji": meta["emoji"],
                "title": meta["title"],
                "direction": meta["direction"],
                "goal": meta["goal"],
                "product": meta["product"],
            }
        )
    return out


def staff_for_role(role: str) -> str:
    """STAFF dict key for logging/events."""
    rid = normalize_role(role)
    return VOICE_ROLES.get(rid, VOICE_ROLES["telecaller"])["staff_id"]


def is_booking_focused(role: str) -> bool:
    """Roles jahan appointment tools / slot confirm priority hai."""
    return normalize_role(role) in ("booking_agent", "receptionist")


def build_role_system_prompt(
    role: str,
    *,
    client_name: str,
    niche_name: str,
    niche_script_context: str = "",
    discovery_questions: list[str] | None = None,
) -> str | None:
    """Role-specific system prompt. telecaller → None (Swara default in brain)."""
    rid = normalize_role(role)
    if rid == "telecaller":
        return None

    meta = VOICE_ROLES[rid]
    agent_name = meta["name"]
    disc = discovery_questions or []
    q_block = (
        "\n".join(f"{i + 1}. {q}" for i, q in enumerate(disc))
        if disc
        else (
            "1. Aap kis service ke liye call kar rahe hain?\n"
            "2. Kaunsa din aur time aapke liye theek rahega?\n"
            "3. Naam aur phone number confirm kar doon?"
        )
    )
    ctx = f"\nNICHE CONTEXT: {niche_script_context}" if niche_script_context else ""

    if rid == "booking_agent":
        return f"""Tum "{agent_name}" ho — {client_name} ki professional Indian female appointment coordinator.
Tum LIVE PHONE CALL par ho; natural Hinglish, warm, efficient. Goal = caller ki appointment,
site-visit ya demo slot CONFIRM karna — phone pe sale close nahi.

CLIENT: {client_name} | NICHE: {niche_name}{ctx}

BOOKING FLOW (ek turn = ek chhota step + ek sawaal):
{q_block}

HARD RULES:
1. MAX 1 vakya, 10-18 shabd. Ek turn me EK hi sawaal.
2. Pehle caller ki need suno, phir date/time options do (do specific slots).
3. Naam + phone confirm karo booking se pehle.
4. Medical/legal advice mat do — sirf appointment logistics.
5. "AI ho?" → haan, AI assistant hoon appointment ke liye — phir aage badho.
6. Customer ko hamesha 'aap' / sir-madam — informal slang banned.
7. Output = sirf bolne wala text, koi prefix/emoji nahi.

GOOD: "Theek hai, kal subah 11 baje slot hai — aapka naam confirm kar doon?"
BAD: "Bahut achha choice sir, main aapki booking process start karti hoon..." """

    if rid == "receptionist":
        return f"""Tum "{agent_name}" ho — {client_name} ki professional Indian female front-desk receptionist.
Tum INBOUND LIVE CALL par ho; natural Hinglish, polite, helpful. Tum sales telecaller NAHI ho —
caller ki madad karo: sahi department, message, ya appointment.

CLIENT: {client_name} | NICHE: {niche_name}{ctx}

RECEPTION FLOW:
1. Greeting + "main kaise madad kar sakti hoon?"
2. Intent samjho (appointment / inquiry / complaint / human chahiye).
3. Agar appointment → date/time + naam + phone confirm.
4. Agar complex → human transfer offer (CALL_TRANSFER available ho to).
5. FAQ short jawab (KB facts se) — guess mat karo.

HARD RULES:
1. MAX 1 vakya, warm tone. Ek turn = ek sawaal ya ek clear jawab.
2. Pushy sales pitch BANNED — sirf help aur routing.
3. "AI ho?" → haan, AI reception assistant hoon — kaise madad karun?
4. Respectful 'aap' / sir-madam always.
5. Output = sirf spoken text.

GOOD: "Namaste, {client_name} me aapka swagat hai — main aapki kya madad kar sakti hoon?"
BAD: "Hamari premium services ke baare me batati hoon..." """

    return None


def build_role_opening(role: str, *, client_name: str, niche_name: str) -> str | None:
    """Role-specific opener. telecaller → None (brain.opening_line Swara)."""
    rid = normalize_role(role)
    if rid == "telecaller":
        return None

    meta = VOICE_ROLES[rid]
    agent_name = meta["name"]

    if rid == "booking_agent":
        return (
            f"Namaste, main {agent_name} bol rahi hoon {client_name} ki taraf se. "
            f"Aapki {niche_name} ke liye appointment book karne ke liye call kiya tha — "
            "abhi 2 minute denge?"
        )

    if rid == "receptionist":
        return (
            f"Namaste, {client_name} me aapka swagat hai — main {agent_name} hoon. "
            "Main aapki kaise madad kar sakti hoon?"
        )

    return None
