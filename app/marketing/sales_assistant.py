"""AI sales-closer — objection handling + push-to-close (inbound chat/WhatsApp/email).

Prospect ka message → objection classify (price/trust/works/timing/info/ready) →
confident Hinglish reply + sahi CTA (demo / pricing / booking). Self-serve close ko
push karta. free-LLM (template fallback). Ban-safe (replies; auto-send channel pe).
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

BASE = "https://leadsgenai.in"

# Objection → ready rebuttal (template) + CTA
REBUTTALS: dict[str, dict[str, str]] = {
    "price": {
        "reply": "Samajh sakta hoon. Socho — ek missed inquiry ka nuksan ₹15-20K ho sakta. ₹1,999/mo us se kam hai, aur pehle 10 leads FREE. Risk zero.",
        "cta": "/pricing",
    },
    "trust": {
        "reply": "Bilkul valid. Isliye 2-min ki live demo hai — khud AI agent se baat karke dekho, phir decide karo. Cancel anytime, koi lock-in nahi.",
        "cta": "/app/test-call",
    },
    "works": {
        "reply": "Kaam karta hai — AI har inquiry ko 2 min me call karke qualify karta hai. 2-min demo suno, aapko khud feel aayega.",
        "cta": "/app/test-call",
    },
    "timing": {
        "reply": "Koi jaldi nahi. Par jab tak wait karenge, leads nikalte rahenge. Free audit le lo abhi — pata chalega kahan paisa ja raha.",
        "cta": "/audit",
    },
    "info": {
        "reply": "Zaroor! Hum AI se aapki marketing + Google ranking + inquiry-calling sambhalte hain. Sabse aasaan — 2-min demo dekho:",
        "cta": "/app/test-call",
    },
    "ready": {
        "reply": "Zabardast! Yahan se 2 min me account + pehle 10 leads FREE shuru ho jaata:",
        "cta": "/pricing",
    },
}
_CATS = list(REBUTTALS.keys())


async def handle_message(
    message: str, business_name: str = "", niche: str = "general", phone: str = ""
) -> dict[str, Any]:
    """Prospect message → objection-aware sales reply + CTA. Kabhi raise nahi.

    `phone` (optional) ho to memory_vault se prospect history LLM context me
    jaati (Rowboat-style compounding memory) — memory na ho = aaj jaisa."""
    msg = (message or "").strip()
    if not msg:
        return {"ok": False, "reason": "empty"}
    intent = "info"
    reply = REBUTTALS["info"]["reply"]
    cta = REBUTTALS["info"]["cta"]

    # Best-effort memory context (never-raise; empty = zero change)
    history = ""
    if phone:
        try:
            from app.platform import memory_vault

            history = memory_vault.context_snippet(phone=phone, max_chars=600)
        except Exception:
            history = ""

    try:
        import json

        from app.voice_agent import free_ai

        sys = (
            "Tum LeadGen AI ke sales-closer ho. Prospect ka message do. Ek JSON lautao: "
            '{"intent":"<price|trust|works|timing|info|ready>","reply":"<confident short Hinglish '
            'reply jo objection handle kare + close pe push kare>"}. Pushy nahi, helpful. Sirf JSON.'
        )
        user_content = f"Business: {business_name}. Niche: {niche}. Msg: {msg}"
        if history:
            user_content = f"History (is prospect ki):\n{history}\n\n{user_content}"
        raw, _ = await free_ai.chat(
            sys,
            [{"role": "user", "content": user_content}],
            max_tokens=200,
            temperature=0.4,
        )
        i, j = raw.find("{"), raw.rfind("}")
        if i != -1 and j != -1:
            d = json.loads(raw[i : j + 1])
            it = str(d.get("intent", "")).lower()
            if it in _CATS:
                intent = it
                cta = REBUTTALS[it]["cta"]
            if isinstance(d.get("reply"), str) and d["reply"].strip():
                reply = d["reply"].strip()
            else:
                reply = REBUTTALS[intent]["reply"]
    except Exception as e:
        logger.debug(f"[sales_assistant] llm skip: {e}")

    return {
        "ok": True,
        "intent": intent,
        "reply": reply,
        "cta_url": BASE + cta,
        "cta_text": {
            "price": "Pricing dekhein",
            "trust": "Live demo",
            "works": "Live demo",
            "timing": "Free audit",
            "info": "Live demo",
            "ready": "Abhi shuru karein",
        }.get(intent, "Live demo"),
        "auto_sent": False,
    }


__all__ = ["handle_message", "REBUTTALS"]
