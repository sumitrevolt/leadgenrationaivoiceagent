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
import os

logger = logging.getLogger(__name__)

_FALLBACK = (
    "Iska jawab main team se confirm karke bata deta hoon — apna number/WhatsApp share "
    "kar dijiye, hum turant contact karenge. 🙏"
)

_GUARDRAIL_BLOCK = (
    "Maaf kijiye, is request me main madad nahi kar sakti. Koi aur sawaal ho to poochhiye. 🙏"
)


def _guardrails_on() -> bool:
    """Public chatbot/widget pe runtime guardrails (PII redact + injection block).
    GATED PUBLIC_GUARDRAILS=1 (default OFF = byte-identical behaviour). The voice path
    already uses guardrails; yeh wahi rule-based module public LLM surface pe wire karta."""
    return (os.getenv("PUBLIC_GUARDRAILS", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _agentic_rag_on() -> bool:
    """Corrective (CRAG) retrieval fallback for the public chatbot — query-rewrite +
    retry + grounded answer when the cheap KB retrieval comes back EMPTY. GATED
    USE_AGENTIC_RAG=1 (default OFF = byte-identical). Closes the wiring gap noted in
    docs/RAG_KnowledgeGraph_Agentic.md (the module had zero call-sites). Never-raise."""
    return (os.getenv("USE_AGENTIC_RAG", "") or "").strip().lower() in ("1", "true", "yes", "on")


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
        return {
            "answer": "Namaste! Boliye, main aapki kaise madad karu?",
            "ask_contact": False,
            "sources": 0,
        }

    # PRE-LLM guardrails (public unauth surface): PII redact + prompt-injection block.
    # GATED PUBLIC_GUARDRAILS=1 (default OFF). Fail-open. Block -> LLM call hi nahi hoti;
    # redacted text hi KB+LLM tak jaata (customer PII free-LLM tak na pahunche).
    _guard = None
    if _guardrails_on():
        try:
            from app.voice_agent.guardrails import get_guardrails

            _guard = get_guardrails()
            _gi = _guard.check_input(q)
            if not _gi.allowed:
                logger.info("chatbot guardrail blocked input: %s", _gi.violations)
                return {"answer": _GUARDRAIL_BLOCK, "ask_contact": False, "sources": 0}
            q = (_gi.text or q).strip() or q  # redacted text aage
        except Exception as e:
            logger.debug("chatbot guardrail input skip (fail-open): %s", e)
            _guard = None

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

    # Corrective fallback (CRAG): agar cheap multi-ns retrieval KHAALI aaya AND
    # USE_AGENTIC_RAG on, to agentic loop (grade → query-rewrite → retry → grounded
    # answer) try karo. SIRF is weak/empty path pe — common path (context mil gaya)
    # bilkul unchanged + zero extra latency. Gated + bounded + never-raise.
    if not ctx and _agentic_rag_on():
        try:
            from app.agents.agentic_rag import get_agentic_rag

            _ns = f"client:{client_id}" if client_id else f"niche:{niche}"
            _ar = await asyncio.wait_for(
                get_agentic_rag().answer(q, namespace=_ns, k=k), timeout=20.0
            )
            _ans = (_ar.get("answer") or "").strip() if isinstance(_ar, dict) else ""
            if _ar.get("ok") and _ar.get("grounded") and _ans:
                if _guard is not None:
                    try:
                        _go = _guard.check_output(_ans)
                        _ans = (_go.text or _ans).strip()
                    except Exception as e:
                        logger.debug("chatbot agentic-RAG output guard skip: %s", e)
                return {
                    "answer": _ans,
                    "ask_contact": False,
                    "sources": len(_ar.get("sources") or []),
                }
        except Exception as e:
            logger.info("chatbot agentic-RAG fallback skip (fail-open): %s", e)

    context = "\n".join(f"- {c}" for c in ctx[:k])
    try:
        from app.cache.semantic_cache import semantic_complete
        from app.voice_agent import free_ai

        async def _gen_answer() -> str:
            ans_text, _ = await asyncio.wait_for(
                free_ai.chat(
                    system="Tu ek business ka friendly customer-support + sales assistant hai. CONTEXT se hi, "
                    "concise Hinglish me (max 3 lines) jawab de. Agar customer buy/visit/price me interested lage "
                    "ya answer context me na ho, to politely uska number/WhatsApp maang (lead capture). Pushy mat ban.",
                    messages=[
                        {
                            "role": "user",
                            "content": f"CONTEXT:\n{context or '(none)'}\n\nCUSTOMER: {q}",
                        }
                    ],
                    max_tokens=120,
                    temperature=0.4,
                ),
                timeout=25.0,
            )
            return (ans_text or "").strip()

        # FAQ-style repeat sawaalon pe semantic cache (latency↓ + free-LLM TPD↓).
        # OFF default (SEMANTIC_CACHE flag) -> _gen_answer() seedha = byte-identical
        # behaviour. Fail-open. scope=client/niche (cross-serve nahi). Answer KB-context
        # pe depend karta isliye TTL (default 6h) staleness bound karta hai.
        ans, _ci = await semantic_complete(q, _gen_answer, scope=(client_id or niche or "general"))
        ans = (ans or "").strip()
        if ans:
            # POST-LLM guardrail: system-prompt-leak / unsafe-promise block -> safe text.
            if _guard is not None:
                try:
                    _go = _guard.check_output(ans)
                    ans = (_go.text or ans).strip()
                except Exception as e:
                    logger.debug("chatbot guardrail output skip (fail-open): %s", e)
            low = ans.lower()
            ask = (not context) or any(w in low for w in ["number", "whatsapp", "contact", "call"])
            return {"answer": ans, "ask_contact": ask, "sources": len(ctx[:k])}
    except Exception as e:
        logger.info("chatbot reply err: %s", e)

    return {"answer": _FALLBACK, "ask_contact": True, "sources": len(ctx[:k])}


__all__ = ["reply"]
