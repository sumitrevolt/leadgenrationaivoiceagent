"""Client-KB → personalized content glue.

AUTO_ONBOARD client website ko KB me seed karta hai (namespace client:<id>) —
yeh module wahi facts retrieve karke caption me inject karta. Generic niche-post
se quality jump, sirf glue (KB/post_generator REBUILD nahi).

Defensive: KB empty / LLM fail → post_generator fallback. NEVER raises.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _namespace(cid: str) -> str:
    try:
        from app.platform.agent_provisioner import _client_namespace

        return _client_namespace(cid)
    except Exception:
        return f"client:{cid}"


def client_context(client_id: str, query: str = "", k: int = 3) -> list[str]:
    """Client KB se top-k facts (text snippets). Empty = KB seed nahi hua."""
    if not (client_id or "").strip():
        return []
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        hits = get_knowledge_base().retrieve(
            query or "services prices offers speciality",
            k=max(1, k),
            namespace=_namespace(client_id),
        )
        return [h.get("text", "")[:300] for h in hits if h.get("text")]
    except Exception as e:
        logger.debug(f"client_context skip: {e}")
        return []


async def personalized_post(
    client_id: str,
    occasion: str = "",
    offer: str = "",
) -> dict[str, Any]:
    """Client ke REAL facts (KB) ke saath post — fallback = normal generate_post."""
    from app.marketing import clients_store, post_generator

    client = clients_store.get_client(client_id) or {}
    name = client.get("business_name") or "Aapka Business"
    niche = client.get("niche") or "general"

    facts = client_context(client_id, query=occasion or offer or "")
    base = await post_generator.generate_post(name, niche=niche, occasion=occasion, offer=offer)

    if not facts:
        return {**base, "personalized": False, "facts_used": []}

    try:
        from app.voice_agent import free_ai

        text, provider = await free_ai.chat(
            "Tu ek Hinglish social-media copywriter hai. Sirf caption likho, 2-3 lines.",
            [
                {
                    "role": "user",
                    "content": (
                        f"Business: {name} ({niche}). Real facts: "
                        + " | ".join(facts[:3])
                        + f". Occasion: {occasion or 'none'}. Offer: {offer or 'none'}. "
                        "In facts me se 1-2 specific cheez use karke catchy Hinglish caption do."
                    ),
                }
            ],
            max_tokens=160,
        )
        caption = (text or "").strip()
        if caption:
            return {
                **base,
                "caption": caption,
                "post_text": caption + "\n\n" + " ".join(base.get("hashtags", [])),
                "personalized": True,
                "facts_used": facts[:3],
                "provider": provider,
            }
    except Exception as e:
        logger.debug(f"personalized_post llm skip: {e}")
    return {**base, "personalized": False, "facts_used": facts[:3]}
