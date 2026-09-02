"""Test-call se auto-learn — Meera lesson + Swara prompt fuel (free LLM, import-safe)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MIN_TURNS = 4


def _turns_to_messages(turns: list[Any] | None) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    for t in turns or []:
        if not isinstance(t, dict):
            continue
        role = str(t.get("role") or "user").lower()
        if role not in ("user", "assistant"):
            role = "assistant" if role in ("bot", "swara", "agent") else "user"
        content = str(t.get("text") or t.get("content") or "").strip()
        if content:
            msgs.append({"role": role, "content": content[:2000]})
    return msgs


async def analyze_web_session(session: dict[str, Any]) -> dict[str, Any]:
    """Ek saved test-call session se lesson likho — galat jawab/stuck patterns fix."""
    turns = session.get("turns") or []
    if len(turns) < _MIN_TURNS:
        return {"ok": False, "reason": "too_short"}

    rec = {
        "niche": session.get("niche") or "general",
        "duration_s": session.get("duration_s") or 0,
        "user_turns": sum(1 for t in turns if (t.get("role") or "") == "user"),
        "stream_sid": session.get("session_id") or "",
        "messages": _turns_to_messages(turns),
        "source": "web_call_test",
    }
    if not rec["messages"]:
        return {"ok": False, "reason": "empty"}

    try:
        from app.agents.eval_metrics import voice_turn_score
        from app.platform import skill_library
        from app.voice_agent import free_ai

        vs = voice_turn_score(rec["messages"])
        score = float(vs.get("score") or 0)
        flags = vs.get("flags") or {}

        tx = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in rec["messages"][-16:])[:3500]

        prompt = (
            f"Niche: {rec['niche']}. Test-call score: {score:.2f} flags={flags}\n\n"
            f"TRANSCRIPT:\n{tx}\n\n"
            "Swara ne customer ke hisaab se sahi jawab diya? 3 Hinglish bullets:\n"
            "(1) customer kya pooch/bola (2) Swara ne kya galat/atak diya (3) agli baar EXACT kya bolna "
            "(1 actionable line). Sirf bullets."
        )
        analysis = ""
        try:
            raw, prov = await free_ai.chat(
                "Voice QA coach — concise Hinglish bullets only.",
                [{"role": "user", "content": prompt}],
                max_tokens=260,
                temperature=0.2,
            )
            if raw and str(raw).strip():
                analysis = f"[{prov}] {str(raw).strip()}"
        except Exception as e:
            logger.debug("web_call_learn: llm skip (%s)", e)

        if analysis:
            topic = f"voice_{rec['niche']}"
            skill_library.record_lesson(
                topic=topic,
                lesson=f"Web test {str(rec['stream_sid'])[:12]} score={score:.2f} | {analysis[:420]}",
                source="web_call_learn",
                agent="meera",
            )

        skill_library.record_use(
            "web_call_test",
            ok=score >= 0.65 and rec["user_turns"] >= 2,
            detail=f"score={score:.2f} turns={rec['user_turns']}",
            agent="swara",
        )

        # P3c — per-call self-improve GATE: failing calls ke liye structured proposal
        # (better candidate reply + promotion-gate) store karo. NEVER auto-applies to
        # prod; admin review karta. Clean calls = no-op. Never blocks the return.
        proposal_id = None
        try:
            from app.voice_agent.voice_self_improve import propose_from_session

            _p = await propose_from_session(session, rec["messages"], score, flags)
            proposal_id = (_p or {}).get("id")
        except Exception as e:
            logger.debug("web_call_learn: self-improve proposal skip (%s)", e)

        return {"ok": True, "score": score, "analysis": analysis[:200], "proposal_id": proposal_id}
    except Exception as e:
        logger.debug("web_call_learn failed: %s", e)
        return {"ok": False, "reason": str(e)[:80]}
