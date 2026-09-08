"""
Per-call self-improvement GATE (P3c, 2026-06-28)
================================================
Close-the-loop "learn from every call's mistakes" — SAFELY.

Flow (per saved test-call):
  1. classify_failures()  — deterministic failure tags (dodge / dead-air / repeat /
     too-long / unanswered-question) from the transcript + voice_turn_score flags.
  2. propose_from_session() — for a FAILING call, generate a BETTER candidate reply
     (free LLM, bounded) for the worst turn and store a structured PROPOSAL to
     data/voice_proposals.jsonl. **Proposals are NEVER auto-applied to production.**
  3. promotion_gate() — the "only promote if quality improves" check: the candidate
     reply must out-score the actual (failed) reply on voice_turn_score AND obey the
     telecaller rules (≤2 sentences, non-empty, no [placeholder] leak). Deterministic.
  4. Admin reviews + promotes (web_call_admin endpoints). Promotion only flips status;
     applying a fact to the niche KB is a separate, explicit admin action — prompts/
     scripts are never blind-written (matches code_upgrader's "never auto-apply core").

Flag VOICE_SELF_IMPROVE (default ON = propose+store; promotion stays manual/gated).
Import-safe, never raises.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

_STORE = os.path.join("data", "voice_proposals.jsonl")
_PROMOTE_MARGIN = (
    0.0  # candidate must be >= actual (ties allowed when actual already 1.0 fails on rules)
)
_ID_RE = re.compile(r"^vp_[a-f0-9]{8,16}$")


def _enabled() -> bool:
    return (os.environ.get("VOICE_SELF_IMPROVE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _looks_like_question(t: str) -> bool:
    low = (t or "").lower()
    return (
        "?" in low
        or "？" in low
        or any(
            w in low
            for w in (
                "kya",
                "kaise",
                "kitna",
                "kitne",
                "kab",
                "kahan",
                "kaun",
                "kyun",
                "क्या",
                "कैसे",
                "कितन",
            )
        )
    )


def classify_failures(
    messages: list[dict[str, str]], score: float, flags: dict[str, int]
) -> list[str]:
    """Deterministic failure tags for a call. Empty = the call looked clean."""
    tags: list[str] = []
    flags = flags or {}
    if (flags.get("empty") or 0) > 0:
        tags.append("dead_air")
    if (flags.get("repeat") or 0) > 0:
        tags.append("repeat")
    if (flags.get("too_long") or 0) > 0:
        tags.append("too_long")
    if (flags.get("double_question") or 0) > 0:
        tags.append("double_question")
    # Unanswered-question / dodge: a user question whose very next bot reply is itself
    # a question (asks back) instead of answering.
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    for i, m in enumerate(msgs[:-1]):
        if str(m.get("role")) == "user" and _looks_like_question(str(m.get("content", ""))):
            nxt = msgs[i + 1]
            if str(nxt.get("role")) in ("assistant", "bot") and _looks_like_question(
                str(nxt.get("content", ""))
            ):
                # bot answered a question with a question and offered no statement
                if (
                    "?" in str(nxt.get("content", ""))
                    and len(str(nxt.get("content", "")).split()) <= 14
                ):
                    tags.append("unanswered_question")
                    break
    if score < 0.7 and not tags:
        tags.append("low_score")
    return tags


def _worst_turn(messages: list[dict[str, str]]) -> tuple[str, str]:
    """Pick a (user_question, bad_bot_reply) pair for the proposal evidence."""
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    for i, m in enumerate(msgs[:-1]):
        if str(m.get("role")) == "user" and _looks_like_question(str(m.get("content", ""))):
            nxt = msgs[i + 1]
            if str(nxt.get("role")) in ("assistant", "bot"):
                return str(m.get("content", "")), str(nxt.get("content", ""))
    # fallback: last user + last bot
    last_user = next(
        (str(m.get("content", "")) for m in reversed(msgs) if str(m.get("role")) == "user"), ""
    )
    last_bot = next(
        (
            str(m.get("content", ""))
            for m in reversed(msgs)
            if str(m.get("role")) in ("assistant", "bot")
        ),
        "",
    )
    return last_user, last_bot


async def _candidate_reply(niche: str, user_q: str, bad_reply: str) -> str:
    """Free-LLM: a BETTER ≤2-sentence Hinglish reply for the failed turn. Bounded."""
    try:
        import asyncio

        from app.voice_agent import free_ai

        prompt = (
            f"Niche: {niche}. Ek voice telecaller (Swara) ne galti ki.\n"
            f"Customer ne poocha: {user_q[:300]}\n"
            f"Swara ne galat/dodge jawab diya: {bad_reply[:300]}\n\n"
            "Sahi jawab likho: ≤2 chhote Hinglish vakya, customer ke sawaal ka SEEDHA jawab "
            "pehle, phir (zaroorat ho to) ek chhota sawaal. Koi [placeholder]/emoji nahi. "
            "Sirf bola jaane wala text."
        )
        raw, _prov = await asyncio.wait_for(
            free_ai.chat(
                "Voice telecaller coach — output only the corrected spoken reply.",
                [{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.3,
            ),
            timeout=10.0,
        )
        return (raw or "").strip()
    except Exception as e:
        logger.debug("voice_self_improve: candidate gen skip (%s)", e)
        return ""


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE), exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # pragma: no cover
        logger.debug("voice_self_improve: append failed (%s)", e)


async def propose_from_session(
    session: dict[str, Any],
    messages: list[dict[str, str]],
    score: float,
    flags: dict[str, int],
) -> dict[str, Any] | None:
    """For a FAILING call, store a structured improvement proposal. Never auto-applies.
    Returns the proposal dict, or None if the call was clean / disabled."""
    if not _enabled():
        return None
    failures = classify_failures(messages, score, flags)
    if not failures:
        return None
    user_q, bad_reply = _worst_turn(messages)
    candidate = await _candidate_reply(str(session.get("niche") or "general"), user_q, bad_reply)
    proposal = {
        "id": f"vp_{uuid.uuid4().hex[:12]}",
        "ts": _now(),
        "niche": str(session.get("niche") or "general"),
        "session_id": str(session.get("session_id") or "")[:64],
        "score": round(float(score), 4),
        "failures": failures,
        "user_question": user_q[:400],
        "bad_reply": bad_reply[:400],
        "candidate": candidate[:600],
        "status": "proposed",
        "gate": None,
    }
    # Pre-compute the promotion-gate verdict so admin sees it immediately.
    try:
        proposal["gate"] = promotion_gate(proposal)
    except Exception:
        proposal["gate"] = None
    _append(proposal)
    logger.info(
        "voice_self_improve: proposal %s (%s) failures=%s",
        proposal["id"],
        proposal["niche"],
        failures,
    )
    return proposal


def promotion_gate(proposal: dict[str, Any]) -> dict[str, Any]:
    """The "only promote if quality improves" check (deterministic). The candidate
    reply must out-score the actual bad reply on voice_turn_score AND obey telecaller
    rules. Returns {pass, actual_score, candidate_score, reason}."""
    candidate = str(proposal.get("candidate") or "").strip()
    bad = str(proposal.get("bad_reply") or "").strip()
    user_q = str(proposal.get("user_question") or "").strip()
    if not candidate:
        return {"pass": False, "reason": "no_candidate"}
    if "[" in candidate and "]" in candidate:
        return {"pass": False, "reason": "placeholder_leak"}
    try:
        from app.agents.eval_metrics import voice_turn_score

        ctx = [{"role": "user", "content": user_q}] if user_q else []
        cand_score = float(
            voice_turn_score(ctx + [{"role": "assistant", "content": candidate}]).get("score", 0)
        )
        actual_score = (
            float(voice_turn_score(ctx + [{"role": "assistant", "content": bad}]).get("score", 0))
            if bad
            else 0.0
        )
    except Exception as e:
        return {"pass": False, "reason": f"score_error:{str(e)[:40]}"}
    # candidate must answer the question (overlap with a non-question statement) — proxy:
    # it should NOT itself be only-a-question, and should be >= actual.
    only_question = candidate.endswith("?") and len(candidate.split()) <= 8
    ok = (cand_score >= actual_score + _PROMOTE_MARGIN) and not only_question
    return {
        "pass": bool(ok),
        "actual_score": round(actual_score, 4),
        "candidate_score": round(cand_score, 4),
        "reason": "ok" if ok else ("still_a_question" if only_question else "not_better"),
    }


def list_proposals(limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
    """Newest-first proposals (optionally filtered by status). Never raises."""
    if not os.path.isfile(_STORE):
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(_STORE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if status and str(r.get("status")) != status:
                    continue
                rows.append(r)
    except Exception:
        return []
    rows.reverse()
    return rows[: max(1, min(int(limit or 50), 200))]


def set_proposal_status(proposal_id: str, status: str) -> bool:
    """Flip a proposal's status (proposed→promoted/rejected). Rewrites the jsonl.
    Promotion is GATED by promotion_gate at the API layer. Never raises."""
    if not _ID_RE.match(proposal_id or "") or status not in ("promoted", "rejected", "proposed"):
        return False
    if not os.path.isfile(_STORE):
        return False
    try:
        with open(_STORE, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        out, hit = [], False
        for line in lines:
            try:
                r = json.loads(line)
            except Exception:
                out.append(line.rstrip("\n"))
                continue
            if r.get("id") == proposal_id:
                r["status"] = status
                r["status_at"] = _now()
                hit = True
            out.append(json.dumps(r, ensure_ascii=False))
        if hit:
            with open(_STORE, "w", encoding="utf-8") as f:
                f.write("\n".join(out) + "\n")
        return hit
    except Exception:
        return False


__all__ = [
    "classify_failures",
    "propose_from_session",
    "promotion_gate",
    "list_proposals",
    "set_proposal_status",
]
