"""
Agent Provisioner — har naye client ke liye 2 dedicated agents.

Jab system new client banata hai, uske business ke hisab se do agents
auto-provision hote hain:

  1. DATA AGENT  (role="data")  — client ke business ka data sambhalta hai:
     business profile + niche facts knowledge-base me load karta hai taaki
     voice agent grounded jawab de sake; aage enrichment/scraping isi ke
     naam pe chalta hai.

  2. LEADS AGENT (role="leads") — client ke END CUSTOMERS ko call karke
     leads laata hai. Niche ke `target_type` (b2c/b2b/both) ke hisab se
     audience set hota hai aur niche flow + qualification questions use
     karta hai.

Idempotent: same client ke liye dobara call karne par naye agents nahi bante.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentStatus
from app.niches import NICHES
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

AGENT_ROLE_DATA = "data"
AGENT_ROLE_LEADS = "leads"


def resolve_niche_key(value: str | None) -> str:
    """
    Map a client's industry/niche string to a NICHES key.
    Accepts exact keys ("solar_residential"), display names ("Residential
    Rooftop Solar"), or loose words ("solar", "real estate"). Falls back to
    "digital_marketing"-agnostic 'general' string if nothing matches.
    """
    if not value:
        return "general"
    v = value.strip().lower().replace(" ", "_")
    if v in NICHES:
        return v
    # name match
    for key, cfg in NICHES.items():
        if cfg.get("name", "").strip().lower() == value.strip().lower():
            return key
    # loose contains-match (e.g. "solar" → first solar niche; "real estate")
    loose = value.strip().lower()
    for key, cfg in NICHES.items():
        if loose in key.replace("_", " ") or loose in cfg.get("name", "").lower():
            return key
    return "general"


def _short_code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def _client_namespace(client_id: str) -> str:
    return f"client:{client_id}"


def _seed_client_knowledge(client: Any, niche_key: str) -> int:
    """
    Client-specific facts knowledge-base me daalo (best-effort — KB na ho
    to silently skip). Yeh data agent ka pehla kaam hai.
    """
    try:
        from app.voice_agent.kb_loader import bootstrap_default_kb

        kb = bootstrap_default_kb()  # pre-loaded singleton
    except Exception:
        try:
            from app.voice_agent.knowledge_base import KnowledgeBase

            kb = KnowledgeBase()
        except Exception as e:  # pragma: no cover
            logger.warning(f"KB unavailable, skipping client knowledge seed: {e}")
            return 0

    cfg = NICHES.get(niche_key, {})
    ns = _client_namespace(str(client.id))
    facts: list[str] = [
        f"Client business: {client.business_name}."
        + (f" Industry: {client.industry}." if getattr(client, "industry", None) else ""),
        f"Contact: {client.contact_name} ({client.contact_phone})."
        + (f" City: {client.city}." if getattr(client, "city", None) else ""),
    ]
    if cfg:
        facts.append(
            f"{client.business_name} operates in the '{cfg.get('name', niche_key)}' niche. "
            f"Typical deal value: {cfg.get('avg_ticket_inr', cfg.get('avg_deal_value', 'varies'))}."
        )
        if cfg.get("end_customer"):
            facts.append(
                f"The leads agent calls this client's end customers: {cfg['end_customer']}"
            )
        if cfg.get("pitch_hook"):
            facts.append(f"Pitch angle for {client.business_name}: {cfg['pitch_hook']}")
        for q in cfg.get("qualification_questions", []):
            facts.append(f"Qualification question for {cfg.get('name', niche_key)} leads: {q}")
    # Niche knowledge pack — data agent inhe client KB me seed karta hai taaki
    # leads agent end-customer ke sawaalon ka grounded (sach) jawab de sake.
    try:
        from app.niche_knowledge import knowledge_facts

        facts.extend(knowledge_facts(niche_key))
    except Exception as e:  # pragma: no cover
        logger.debug(f"niche knowledge seed skipped: {e}")
    try:
        added = kb.add_documents(facts, source=f"provisioner:{client.id}", namespace=ns)
        logger.info(f"KB seeded for client {client.id} ({added} facts, ns={ns})")
        return added
    except Exception as e:  # pragma: no cover
        logger.warning(f"KB seed failed for client {client.id}: {e}")
        return 0


async def provision_agents_for_client(
    db: AsyncSession,
    client: Any,
    niche: str | None = None,
) -> dict[str, Any]:
    """
    Ensure the client has its two dedicated agents (data + leads).
    Returns {"created": [...], "existing": [...], "niche_key": str}.
    """
    niche_key = resolve_niche_key(niche or getattr(client, "industry", None))
    cfg = NICHES.get(niche_key, {})
    target_type = cfg.get("target_type", "b2c")

    result = await db.execute(select(Agent).where(Agent.current_client_id == str(client.id)))
    existing = list(result.scalars().all())
    existing_roles = {getattr(a, "role", None) for a in existing}

    created: list[Agent] = []

    if AGENT_ROLE_DATA not in existing_roles:
        data_agent = Agent(
            id=str(uuid.uuid4()),
            name=f"{client.business_name} · Data Agent",
            agent_code=_short_code("DA"),
            role=AGENT_ROLE_DATA,
            current_client_id=str(client.id),
            current_client_name=client.business_name,
            niche=niche_key,
            status=AgentStatus.IDLE,
            language="hinglish",
        )
        db.add(data_agent)
        created.append(data_agent)

    if AGENT_ROLE_LEADS not in existing_roles:
        leads_agent = Agent(
            id=str(uuid.uuid4()),
            name=f"{client.business_name} · Leads Agent ({target_type.upper()})",
            agent_code=_short_code("LA"),
            role=AGENT_ROLE_LEADS,
            current_client_id=str(client.id),
            current_client_name=client.business_name,
            niche=niche_key,
            status=AgentStatus.IDLE,
            language="hinglish",
        )
        db.add(leads_agent)
        created.append(leads_agent)

    if created:
        await db.flush()

    # Data agent ka pehla kaam: client knowledge seed (best-effort).
    _seed_client_knowledge(client, niche_key)

    try:  # Team activity: Dev (KB seed) + Rohan (leads agent ready)
        from app.platform.team import log_event

        log_event(
            "dev",
            "kb_seeded",
            f"{client.business_name}: business profile + {niche_key} facts KB me seeded",
        )
        if created:
            log_event(
                "rohan",
                "agents_provisioned",
                f"{client.business_name}: {len(created)} agent(s) ready ({niche_key}, {target_type})",
            )
    except Exception:
        pass

    logger.info(
        f"Agents provisioned for client {client.id}: "
        f"created={[a.agent_code for a in created]}, existing={len(existing)}"
    )
    return {
        "niche_key": niche_key,
        "target_type": target_type,
        "created": [_agent_dict(a) for a in created],
        "existing": [_agent_dict(a) for a in existing],
    }


def _agent_dict(a: Agent) -> dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "agent_code": a.agent_code,
        "role": getattr(a, "role", None),
        "niche": a.niche,
        "client_id": a.current_client_id,
        "status": a.status.value if getattr(a, "status", None) else None,
    }
