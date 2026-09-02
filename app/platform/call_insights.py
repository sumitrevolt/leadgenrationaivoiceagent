"""'Ask AI' over call/lead data — Vodex-style natural-language insights (Hinglish).

"Aaj kitne log interested the?", "callbacks kitne pending?" — admin saadhe sawaal
pooche, AI call/lead data padh ke jawab de. Sources (sab best-effort, jo mile):
  - data/call_qualifications.jsonl  (post-call AI qualifier — call_manager likhta)
  - data/call_transcripts/*.jsonl     (LIVE Vobiz stream full transcripts — vobiz_stream)
  - data/dialer_logs.jsonl          (human dialer dispositions — dialer_log.py)
  - data/cadence_runs.jsonl         (omnichannel cadence step drafts — cadence.py)
  - agent_events                    (team.recent_events helper, lazy/DB-optional)

Design: quick_stats() = PURE-python counts (LLM-free, hamesha kaam). ask() =
compact context (recent N=50, truncated) → free_ai Hinglish answer; LLM fail =
stats-based fallback answer (phir bhi useful). Never raises. Koi flag nahi
(read-only analytics — side-effect zero).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_QUALIFICATIONS = os.path.join("data", "call_qualifications.jsonl")
_DIALER_LOGS = os.path.join("data", "dialer_logs.jsonl")
_CADENCE_RUNS = os.path.join("data", "cadence_runs.jsonl")


def _TRANSCRIPTS_DIR() -> str:
    """Live call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return str(call_transcripts_dir())


_RECENT_N = 50  # context me kitne recent records


def _read_jsonl_tail(path: str, limit: int = _RECENT_N) -> list[dict[str, Any]]:
    """JSONL file ke aakhri `limit` valid records (oldest→newest). Never raises."""
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[call_insights] read {path} failed: {e}")
    return out[-max(1, min(int(limit or _RECENT_N), 500)) :]


def _read_call_transcripts(limit: int = _RECENT_N) -> list[dict[str, Any]]:
    """LIVE Vobiz stream transcripts (data/call_transcripts/YYYY-MM-DD.jsonl). Never raises."""
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isdir(_TRANSCRIPTS_DIR()):
            return out
        files = sorted(f for f in os.listdir(_TRANSCRIPTS_DIR()) if f.endswith(".jsonl"))
        # Last ~14 daily files (newest last for tail read)
        for name in files[-14:]:
            fp = os.path.join(_TRANSCRIPTS_DIR(), name)
            try:
                with open(fp, encoding="utf-8") as f:
                    for ln in f:
                        try:
                            rec = json.loads(ln)
                            if isinstance(rec, dict):
                                out.append(rec)
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"[call_insights] read transcripts failed: {e}")
    return out[-max(1, min(int(limit or _RECENT_N), 200)) :]


def _recent_agent_events(limit: int = 30) -> list[dict[str, Any]]:
    """agent_events via EXISTING team.recent_events (lazy, DB na ho = [])."""
    try:
        from app.platform import team

        evs = team.recent_events(limit=limit) or []
        return [e for e in evs if isinstance(e, dict)]
    except Exception as e:
        logger.debug(f"[call_insights] agent_events skipped: {e}")
        return []


def quick_stats() -> dict[str, Any]:
    """Pure-python counts — LLM-free, kabhi fail nahi (fallback answers ka base)."""
    try:
        quals = _read_jsonl_tail(_QUALIFICATIONS, 500)
        dialer = _read_jsonl_tail(_DIALER_LOGS, 500)
        cadence = _read_jsonl_tail(_CADENCE_RUNS, 500)
        transcripts = _read_call_transcripts(500)

        today = datetime.now(timezone.utc).date().isoformat()

        q_total = len(quals)
        q_qualified = sum(1 for q in quals if q.get("qualified"))
        q_appt = sum(1 for q in quals if q.get("appointment_requested"))
        scores = [int(q.get("interest_score") or 0) for q in quals]
        q_avg = round(sum(scores) / len(scores), 2) if scores else 0.0
        q_budget = dict(Counter(str(q.get("budget_signal") or "unknown") for q in quals))

        d_by = dict(Counter(str(r.get("disposition") or "?") for r in dialer))
        d_today = sum(1 for r in dialer if str(r.get("at") or "")[:10] == today)

        c_by_channel = dict(Counter(str(r.get("channel") or "?") for r in cadence))

        t_today = sum(1 for t in transcripts if str(t.get("ts") or "")[:10] == today)
        t_durs = [
            float(t.get("duration_s") or 0) for t in transcripts if t.get("duration_s") is not None
        ]
        t_avg_dur = round(sum(t_durs) / len(t_durs), 1) if t_durs else 0.0

        return {
            "calls_qualified": {
                "total": q_total,
                "qualified": q_qualified,
                "appointments_requested": q_appt,
                "avg_interest_score": q_avg,
                "by_budget_signal": q_budget,
            },
            "dialer": {
                "total_logged": len(dialer),
                "today": d_today,
                "by_disposition": d_by,
            },
            "cadence": {"recent_steps": len(cadence), "by_channel": c_by_channel},
            "live_calls": {
                "total": len(transcripts),
                "today": t_today,
                "avg_duration_s": t_avg_dur,
                "total_user_turns": sum(int(t.get("user_turns") or 0) for t in transcripts),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"[call_insights] quick_stats failed: {e}")
        return {"error": str(e)[:200]}


def _compact(rec: dict[str, Any], keys: tuple[str, ...], maxlen: int = 90) -> str:
    parts = []
    for k in keys:
        v = rec.get(k)
        if v in (None, "", [], {}):
            continue
        parts.append(f"{k}={str(v)[:maxlen]}")
    return " | ".join(parts)


def _build_context() -> str:
    """Recent records ka compact text-context (LLM token-budget safe)."""
    lines: list[str] = []

    quals = _read_jsonl_tail(_QUALIFICATIONS, _RECENT_N)
    if quals:
        lines.append("## Call qualifications (post-call AI):")
        for q in quals[-25:]:
            lines.append(
                "- "
                + _compact(
                    q,
                    (
                        "call_id",
                        "interest_score",
                        "qualified",
                        "appointment_requested",
                        "budget_signal",
                        "summary",
                    ),
                )
            )

    transcripts = _read_call_transcripts(_RECENT_N)
    if transcripts:
        lines.append("## LIVE phone transcripts (Vobiz stream):")
        for t in transcripts[-15:]:
            lines.append(
                "- "
                + _compact(
                    t,
                    ("stream_sid", "niche", "client_name", "duration_s", "user_turns", "ts"),
                )
            )
            msgs = t.get("messages") or []
            if isinstance(msgs, list) and msgs:
                last_user = next(
                    (m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"),
                    "",
                )
                if last_user:
                    lines.append(f"  last_caller: {str(last_user)[:120]}")

    dialer = _read_jsonl_tail(_DIALER_LOGS, _RECENT_N)
    if dialer:
        lines.append("## Dialer dispositions (human telecaller):")
        for r in dialer[-25:]:
            lines.append("- " + _compact(r, ("phone", "disposition", "notes", "at")))

    cadence = _read_jsonl_tail(_CADENCE_RUNS, _RECENT_N)
    if cadence:
        lines.append("## Cadence steps (outreach sequence):")
        for r in cadence[-15:]:
            lines.append("- " + _compact(r, ("phone", "channel", "action", "day", "at")))

    events = _recent_agent_events(20)
    if events:
        lines.append("## AI staff events:")
        for e in events[:15]:
            lines.append("- " + _compact(e, ("member", "action", "detail", "created_at")))

    return "\n".join(lines)[:6000]


def _stats_answer(stats: dict[str, Any]) -> str:
    """LLM-down fallback — stats se seedha Hinglish jawab (phir bhi useful)."""
    try:
        q = stats.get("calls_qualified") or {}
        d = stats.get("dialer") or {}
        c = stats.get("cadence") or {}
        lc = stats.get("live_calls") or {}
        disp = d.get("by_disposition") or {}
        return (
            f"📊 Data snapshot: {q.get('total', 0)} AI-qualified calls "
            f"({q.get('qualified', 0)} qualified, {q.get('appointments_requested', 0)} appointment, "
            f"avg interest {q.get('avg_interest_score', 0)}/5). "
            f"LIVE calls logged: {lc.get('total', 0)} (aaj {lc.get('today', 0)}, "
            f"avg {lc.get('avg_duration_s', 0)}s). "
            f"Dialer: {d.get('total_logged', 0)} dispositions (aaj {d.get('today', 0)}) — "
            f"interested {disp.get('interested', 0)}, callback {disp.get('callback', 0)}, "
            f"no-answer {disp.get('no-answer', 0)}. "
            f"Cadence: {c.get('recent_steps', 0)} recent outreach steps. "
            f"(AI summary abhi available nahi — yeh direct counts hain.)"
        )
    except Exception:
        return "Data abhi padh nahi paya — thodi der me dobara try karo."


async def ask(question: str) -> dict[str, Any]:
    """NL question over call/lead data → Hinglish answer. Never raises.

    LLM fail/empty = stats-based fallback answer (counts pure-python).
    """
    q = (question or "").strip()
    stats = quick_stats()
    if len(q) < 3:
        return {"ok": False, "answer": _stats_answer(stats), "stats": stats, "provider": ""}
    try:
        context = _build_context()
        if not context.strip():
            return {
                "ok": True,
                "answer": "Abhi koi call/dialer data nahi hai — pehle kuch calls/dispositions hone do.",
                "stats": stats,
                "provider": "",
            }
        from app.voice_agent import free_ai

        reply, provider = await free_ai.chat(
            system=(
                "Tu ek call-analytics assistant hai. Neeche call qualifications, dialer "
                "dispositions, cadence steps ka recent data hai. User ke sawaal ka jawab "
                "SIRF is data se do — 3-5 line Hinglish, numbers ke saath, ek actionable "
                "suggestion end me. Data me nahi hai to saaf bolo 'data me nahi mila'."
            ),
            messages=[{"role": "user", "content": f"DATA:\n{context}\n\nSAWAAL: {q[:300]}"}],
            max_tokens=260,
            temperature=0.2,
        )
        answer = (reply or "").strip()
        if answer:
            return {"ok": True, "answer": answer, "stats": stats, "provider": provider}
    except Exception as e:
        logger.info(f"[call_insights] ask LLM failed: {e}")
    return {"ok": True, "answer": _stats_answer(stats), "stats": stats, "provider": ""}


def list_qualifications(limit: int = 50) -> list[dict[str, Any]]:
    """Recent post-call AI qualifications (newest first). Never raises."""
    try:
        rows = _read_jsonl_tail(_QUALIFICATIONS, max(1, min(int(limit or 50), 200)))
        return list(reversed(rows))
    except Exception as e:
        logger.debug(f"[call_insights] list_qualifications failed: {e}")
        return []


__all__ = ["ask", "quick_stats", "list_qualifications"]
