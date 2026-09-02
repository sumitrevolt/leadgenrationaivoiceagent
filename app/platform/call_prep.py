"""Call Prep — Rowboat "prep me for my meeting with X" ka telecaller avatar.

Human dialer / AI sales agent ko call se PEHLE ek Hinglish brief: kaun hai,
history, pain points, talking points, objections+jawab, next action. Sources:
memory_vault snippet + prospector record + lead score → free-LLM polish
(wait_for 25s), STATIC fallback (kabhi empty nahi). Import-safe, never raises.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _prospect_record(ph10: str) -> dict[str, Any]:
    """prospects.jsonl me phone-match record (best-effort). Kabhi raise nahi."""
    if not ph10:
        return {}
    try:
        from app.platform import prospector
        from app.platform.memory_vault import phone10

        for p in prospector.list_prospects(limit=2000):
            if phone10(p.get("phone")) == ph10:
                return p if isinstance(p, dict) else {}
    except Exception as e:
        logger.debug(f"[prep] prospect lookup skip: {e}")
    return {}


def _score(rec: dict[str, Any]) -> int | None:
    try:
        if not rec:
            return None
        from app.platform.prospect_lists import _scorer_for

        scorer, _ver = _scorer_for()
        return scorer(rec) if scorer else None
    except Exception as e:
        logger.debug(f"[prep] score skip: {e}")
    return None


def _static_brief(ph10: str, rec: dict[str, Any], snippet: str, client_id: str) -> dict[str, Any]:
    """Never-empty fallback brief raw facts se."""
    biz = str(rec.get("business_name") or "").strip()
    niche = str(rec.get("niche") or "").replace("_", " ").strip()
    city = str(rec.get("city") or "").strip()
    kaun = biz or (f"Client {client_id}" if client_id else f"Prospect {ph10 or '?'}")
    if niche or city:
        kaun += f" ({niche}{', ' + city if city else ''})"
    history = (
        snippet.splitlines()[-1][:200] if snippet else "Pehli baar baat ho rahi — koi history nahi."
    )
    return {
        "kaun_hai": kaun,
        "history_summary": history,
        "pain_points": [
            "Inquiries ka follow-up time pe nahi ho pata",
            "Google pe visibility/reviews kam",
        ],
        "talking_points": [
            f"Namaste! {biz or 'Aapke business'} ke liye ek kaam ki baat thi",
            "Har inquiry ka 2-min me AI follow-up — koi lead miss nahi",
            "Marketing + Google + reviews sab automated, ₹1,999/mo se shuru",
            "Free GBP audit abhi bhej sakta hoon — leadsgenai.in/audit",
        ],
        "objections": [
            {
                "objection": "Mehnga lagega",
                "jawab": "Ek missed inquiry ₹15-20K ki hoti — ₹1,999/mo us se kam, pehle 10 leads FREE.",
            },
            {
                "objection": "AI pe bharosa nahi",
                "jawab": "2-min live demo karke khud sun lo — leadsgenai.in/app/test-call. Cancel anytime.",
            },
        ],
        "next_action": "Free audit link WhatsApp karo + 2-min demo offer karo",
        "best_time_hint": "11am-1pm ya 4-6pm (business khula, rush kam)",
    }


async def prep_brief(phone: str | None = None, client_id: str | None = None) -> dict[str, Any]:
    """Call-prep brief (Hinglish). LLM 25s cap, static fallback. Kabhi raise nahi."""
    try:
        import asyncio
        import json as _json

        from app.platform import memory_vault

        ph10 = memory_vault.phone10(phone) if phone else ""
        cid = (client_id or "").strip()
        if not ph10 and not cid:
            return {"ok": False, "error": "phone ya client_id chahiye"}

        snippet = memory_vault.context_snippet(phone=ph10 or None, client_id=cid or None)
        rec = _prospect_record(ph10)
        score = _score(rec)
        brief = _static_brief(ph10, rec, snippet, cid)
        provider = "fallback"

        try:
            from app.voice_agent import free_ai

            facts = _json.dumps(
                {
                    "business_name": rec.get("business_name"),
                    "niche": rec.get("niche"),
                    "city": rec.get("city"),
                    "status": rec.get("status"),
                    "rating": rec.get("rating"),
                    "lead_score": score,
                },
                ensure_ascii=False,
            )
            sys = (
                "Tum ek sales call-prep assistant ho (India, Hinglish). Prospect ka data + history "
                'doonga. SIRF ek JSON lautao: {"kaun_hai":"1 line","history_summary":"1-2 line",'
                '"pain_points":[2-3],"talking_points":[3-5 short],'
                '"objections":[{"objection":"..","jawab":".."} x2-3],'
                '"next_action":"1 line","best_time_hint":"1 line"}. Hinglish, confident, koi extra text nahi.'
            )
            raw, provider = await asyncio.wait_for(
                free_ai.chat(
                    sys,
                    [
                        {
                            "role": "user",
                            "content": f"Data: {facts}\nHistory:\n{(snippet or 'koi history nahi')[:1200]}",
                        }
                    ],
                    max_tokens=450,
                    temperature=0.4,
                ),
                timeout=25,
            )
            i, j = raw.find("{"), raw.rfind("}")
            if i != -1 and j > i:
                d = _json.loads(raw[i : j + 1])
                for k in ("kaun_hai", "history_summary", "next_action", "best_time_hint"):
                    if isinstance(d.get(k), str) and d[k].strip():
                        brief[k] = d[k].strip()[:300]
                for k in ("pain_points", "talking_points"):
                    if isinstance(d.get(k), list) and d[k]:
                        brief[k] = [str(x).strip()[:200] for x in d[k] if str(x).strip()][:5]
                if isinstance(d.get("objections"), list) and d["objections"]:
                    objs = []
                    for o in d["objections"][:3]:
                        if isinstance(o, dict) and o.get("objection") and o.get("jawab"):
                            objs.append(
                                {
                                    "objection": str(o["objection"])[:150],
                                    "jawab": str(o["jawab"])[:250],
                                }
                            )
                    if objs:
                        brief["objections"] = objs
        except Exception as e:
            logger.debug(f"[prep] llm skip: {e}")
            provider = "fallback"

        return {
            "ok": True,
            "phone": ph10 or None,
            "client_id": cid or None,
            "score": score,
            "memory_found": bool(snippet),
            "brief": brief,
            "provider": provider,
        }
    except Exception as e:
        logger.warning(f"[prep] failed: {e}")
        return {"ok": False, "error": str(e)}


__all__ = ["prep_brief"]
