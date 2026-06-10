"""AI FAQ + lead-capture chatbot — customer-facing, grounded in the client's KB.

Competitors (Tidio/Elfsight/Katrix) sell a website chatbot trained on the business's data
that answers customers 24/7 AND captures leads. Onboarding ab har client ki website se KB
seed karta hai (ns `client:<id>`), to har client ka apna bot ho sakta hai — free_ai +
knowledge_base se. Powers a future embeddable website/WhatsApp widget.

reply(question, client_id, niche) -> {answer, ask_contact, sources}  (never raises)
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_FALLBACK = (
    "Iska jawab main team se confirm karke bata deta hoon — apna number/WhatsApp share "
    "kar dijiye, hum turant contact karenge. 🙏"
)


def _kb_context_sync(q: str, client_id: str, niche: str, k: int) -> list[str]:
    """SYNC KB retrieval — SIRF thread me chalao (model first-load + embed = heavy
    sync CPU/network; event loop pe chala to HTTP starve — qa-job prod-down lesson)."""
    ctx: list[str] = []
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        namespaces = ([f"client:{client_id}"] if client_id else []) + [f"niche:{niche}", "default"]
        for ns in namespaces:
            try:
                hits = kb.retrieve(q, k=k, namespace=ns)
                ctx += [h.get("text", "") for h in (hits or []) if h.get("text")]
            except Exception:
                pass
            if len(ctx) >= k:
                break
    except Exception:
        pass
    return ctx


async def reply(question: str, client_id: str = "", niche: str = "general", k: int = 3) -> dict:
    q = (question or "").strip()
    if not q:
        return {"answer": "Namaste! Boliye, main aapki kaise madad karu?", "ask_contact": False, "sources": 0}

    # KB retrieval thread me + hard timeout — event loop KABHI block nahi hota.
    # (Fresh container me fastembed model first-load minutes le sakta hai → us request
    # ko fallback milega, baad ki requests ko loaded model.)
    ctx: list[str] = []
    try:
        ctx = await asyncio.wait_for(
            asyncio.to_thread(_kb_context_sync, q, client_id, niche, k), timeout=10.0
        )
    except (asyncio.TimeoutError, Exception) as e:
        logger.info("chatbot KB skip (timeout/err): %s", e)

    context = "\n".join(f"- {c}" for c in ctx[:k])
    try:
        from app.voice_agent import free_ai

        ans_text, _ = await asyncio.wait_for(
            free_ai.chat(
                system="Tu ek business ka friendly customer-support + sales assistant hai. CONTEXT se hi, "
                "concise Hinglish me (max 3 lines) jawab de. Agar customer buy/visit/price me interested lage "
                "ya answer context me na ho, to politely uska number/WhatsApp maang (lead capture). Pushy mat ban.",
                messages=[{"role": "user", "content": f"CONTEXT:\n{context or '(none)'}\n\nCUSTOMER: {q}"}],
                max_tokens=120,
                temperature=0.4,
            ),
            timeout=25.0,
        )
        ans = (ans_text or "").strip()
        if ans:
            low = ans.lower()
            ask = (not context) or any(w in low for w in ["number", "whatsapp", "contact", "call"])
            return {"answer": ans, "ask_contact": ask, "sources": len(ctx[:k])}
    except Exception as e:
        logger.info("chatbot reply err: %s", e)

    return {"answer": _FALLBACK, "ask_contact": True, "sources": len(ctx[:k])}


__all__ = ["reply"]
