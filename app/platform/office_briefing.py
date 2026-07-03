"""F4 "Subah ki Briefing" — daily Hinglish HQ radio bulletin (text + Swara audio).

A short 6-8 line spoken bulletin for /app/office: collects REAL operational
numbers (overdue/failed jobs, DLQ depth, hot-queue count, today's top active
agents, new/qualified leads), composes them into a Hinglish radio-bulletin via
the FREE LLM chain (`free_ai.chat`), then renders Swara's voice (EdgeTTS
`hi-IN-SwaraNeural`) to an mp3.

Hard rules (match office_hq.py):
  - READ-ONLY. Every number is a direct read of an existing store/builder; no
    new DB models. Never fabricated — a source that fails contributes 0/None.
  - Never raises. Each collector is try/except with a safe default; the compose
    step degrades LLM-fail -> deterministic template, TTS-fail -> text-only.
  - One LLM + one TTS call per IST-day: results cached to
    data/office_briefing/{date}.json + {date}.mp3 (force=True regenerates).
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))

# Module-level so tests can monkeypatch to tmp_path (never write into real data/).
_DIR = "data/office_briefing"

# Swara — EdgeTTS hi-IN-SwaraNeural via the existing voice-stack TTS helper.
_TTS_VOICE_PRESET = "hindi_female"

_SYSTEM = (
    "Tu LeadGenAI ke Operating HQ ka subah ka radio-announcer hai. Tujhe aaj ke "
    "REAL business numbers diye jayenge. In numbers se ek chhota, energetic "
    "Hinglish (Roman script) radio-bulletin bana — jaise koi office ke intercom "
    "par subah ki khabar sunata hai. Rules: SIRF diye gaye numbers use kar (koi "
    "naya number mat bana), zyada se zyada 8 lines, har line chhoti, warm aur "
    "action-oriented. Koi heading/emoji/bullet nahi — sirf bolne wali lines."
)


def _ist_date() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def _json_path(date: str) -> str:
    return os.path.join(_DIR, f"{date}.json")


def _mp3_path(date: str) -> str:
    return os.path.join(_DIR, f"{date}.mp3")


# --------------------------------------------------------------------------- #
# Collectors — each never-raises, contributes a safe default on failure.
# --------------------------------------------------------------------------- #
def _collect_numbers() -> dict[str, Any]:
    """Gather the REAL operational numbers the bulletin will cite."""
    nums: dict[str, Any] = {
        "overdue_jobs": 0,
        "failed_jobs": 0,
        "dlq_depth": 0,
        "hot_queue": 0,
        "new_leads": 0,
        "qualified_leads": 0,
        "top_agents": [],  # list[{"name": str, "count": int}]
    }

    # Automation health — overdue jobs + DLQ depth (failed Celery tasks).
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        nums["overdue_jobs"] = len(h.get("overdue") or [])
        q = h.get("queue") or {}
        nums["dlq_depth"] = int(q.get("dlq") or 0)
        nums["failed_jobs"] = int(q.get("dlq") or 0) + int(q.get("dead") or 0)
    except Exception as e:
        logger.debug(f"[office_briefing] automation_health skipped: {e}")

    # Hot Queue — interested/question replies awaiting a human (reply_agent).
    try:
        from app.platform import reply_agent

        nums["hot_queue"] = len(reply_agent.hot_queue(limit=200) or [])
    except Exception as e:
        logger.debug(f"[office_briefing] hot_queue skipped: {e}")

    # Today's top-3 active agents by event count (team.recent_events, 24h window).
    try:
        from app.platform import team

        events = team.recent_events(limit=2000, hours=24) or []
        counts: dict[str, dict[str, Any]] = {}
        for ev in events:
            member = ev.get("member") or "system"
            if member == "system":
                continue
            entry = counts.setdefault(member, {"name": ev.get("name") or member, "count": 0})
            entry["count"] += 1
        top = sorted(counts.values(), key=lambda x: x["count"], reverse=True)[:3]
        nums["top_agents"] = [{"name": t["name"], "count": int(t["count"])} for t in top]
    except Exception as e:
        logger.debug(f"[office_briefing] top_agents skipped: {e}")

    # New + qualified leads today (IST-day, lead_score >= 70 = qualified).
    try:
        nl, ql = _leads_today()
        nums["new_leads"] = nl
        nums["qualified_leads"] = ql
    except Exception as e:
        logger.debug(f"[office_briefing] leads_today skipped: {e}")

    return nums


def _today_start_utc_naive() -> datetime:
    """IST midnight expressed as naive-UTC (matches office_hq.build_metrics)."""
    n = datetime.now(_IST).replace(hour=0, minute=0, second=0, microsecond=0)
    return n.astimezone(timezone.utc).replace(tzinfo=None)


def _leads_today() -> tuple[int, int]:
    """(new_today, qualified_today) via a bounded sync DB read. Never raises."""
    try:
        from sqlalchemy import select

        from app.models import base as _b
        from app.models.lead import Lead

        _b._get_sync_engine()
        if _b._SessionLocal is None:
            return 0, 0
        today = _today_start_utc_naive()
        new_today = 0
        qualified_today = 0
        db = _b._SessionLocal()
        try:
            rows = db.execute(select(Lead).limit(3000)).scalars().all()
        finally:
            db.close()
        for lead in rows:
            created = getattr(lead, "created_at", None)
            if created is not None and created.replace(tzinfo=None) >= today:
                new_today += 1
                if int(getattr(lead, "lead_score", 0) or 0) >= 70:
                    qualified_today += 1
        return new_today, qualified_today
    except Exception as e:
        logger.debug(f"[office_briefing] _leads_today skipped: {e}")
        return 0, 0


# --------------------------------------------------------------------------- #
# Compose — LLM bulletin, deterministic template fallback.
# --------------------------------------------------------------------------- #
def _template_bulletin(nums: dict[str, Any]) -> str:
    """Deterministic Hinglish bulletin straight from the numbers — used when the
    LLM is unavailable. Still cites every real number so it stays useful."""
    lines = ["Subah ki briefing — aaj ka office update."]
    lines.append(
        f"Aaj {nums['new_leads']} naye leads aaye, jisme se {nums['qualified_leads']} qualified hue."
    )
    top = nums.get("top_agents") or []
    if top:
        names = ", ".join(f"{t['name']} ({t['count']})" for t in top)
        lines.append(f"Sabse active team members: {names}.")
    else:
        lines.append("Abhi tak kisi agent ki activity record nahi hui.")
    lines.append(f"Reception ke Hot Queue me {nums['hot_queue']} garam replies kaam ke liye pending hain.")
    if nums["overdue_jobs"] or nums["failed_jobs"] or nums["dlq_depth"]:
        lines.append(
            f"Reliability: {nums['overdue_jobs']} jobs overdue, DLQ me {nums['dlq_depth']} failed tasks — "
            "inhe repair karna hai."
        )
    else:
        lines.append("Reliability side clean hai — koi overdue job ya failed task nahi.")
    lines.append("Chaliye, aaj ka din shuru karte hain!")
    return "\n".join(lines)


async def _compose_text(nums: dict[str, Any]) -> str:
    """LLM bulletin (one bounded call); on any failure -> template fallback."""
    top = nums.get("top_agents") or []
    top_str = ", ".join(f"{t['name']}={t['count']}" for t in top) or "koi nahi"
    user = (
        "Aaj ke REAL numbers:\n"
        f"- Naye leads: {nums['new_leads']}\n"
        f"- Qualified leads: {nums['qualified_leads']}\n"
        f"- Hot Queue (pending replies): {nums['hot_queue']}\n"
        f"- Overdue jobs: {nums['overdue_jobs']}\n"
        f"- Failed/DLQ tasks: {nums['failed_jobs']} (DLQ depth {nums['dlq_depth']})\n"
        f"- Aaj ke top active agents (naam=events): {top_str}\n"
        "In numbers se subah ki Hinglish radio-briefing bana (max 8 short lines)."
    )
    try:
        from app.voice_agent import free_ai

        text, _provider = await asyncio.wait_for(
            free_ai.chat(
                _SYSTEM,
                [{"role": "user", "content": user}],
                max_tokens=300,
                temperature=0.6,
                scope="office_briefing",
            ),
            timeout=25.0,
        )
        text = (text or "").strip()
        if not text:
            raise ValueError("empty LLM reply")
        return text
    except Exception as e:
        logger.debug(f"[office_briefing] LLM compose failed -> template: {e}")
        return _template_bulletin(nums)


# --------------------------------------------------------------------------- #
# TTS — thin wrapper so tests can monkeypatch a single function. Never raises
# here; the caller decides has_audio from the return value.
# --------------------------------------------------------------------------- #
async def _tts_to_file(text: str, path: str) -> bool:
    """Render `text` in Swara's voice (EdgeTTS hi-IN-SwaraNeural) to `path`.
    Returns True on success, False on any failure (caller -> has_audio)."""
    from app.voice_agent.tts import TextToSpeech

    tts = TextToSpeech(provider="edge")
    await tts.synthesize_to_file(text, path, voice_preset=_TTS_VOICE_PRESET)
    return True


# --------------------------------------------------------------------------- #
# Public — build_briefing (cached, never-raises).
# --------------------------------------------------------------------------- #
async def build_briefing(force: bool = False) -> dict[str, Any]:
    """Today's HQ bulletin: {ok, date, text, has_audio}.

    Cached one-per-IST-day (json + mp3). `force=True` regenerates. Never raises:
    on total failure returns {ok:False, ...} with a safe shape.
    """
    date = _ist_date()
    try:
        os.makedirs(_DIR, exist_ok=True)
    except Exception as e:
        logger.debug(f"[office_briefing] makedirs skipped: {e}")

    jpath = _json_path(date)
    mpath = _mp3_path(date)

    # Cache hit (before any LLM/TTS work). has_audio re-derived from disk so a
    # stale flag can't promise audio that isn't there.
    if not force:
        try:
            if os.path.exists(jpath):
                with open(jpath, encoding="utf-8") as f:
                    cached = json.load(f) or {}
                return {
                    "ok": True,
                    "date": date,
                    "text": cached.get("text") or "",
                    "has_audio": os.path.exists(mpath),
                    "cached": True,
                }
        except Exception as e:
            logger.debug(f"[office_briefing] cache read skipped: {e}")

    # _collect_numbers is SYNC and touches the DB + every draft/agent-event —
    # run it OFF the event loop with a hard deadline (same rule + pattern as
    # office_hq._safe_collect_live_stats; blocking the loop = documented prod-down
    # class). On timeout/failure degrade to zeros so a slow store never hangs the
    # briefing (the template still renders a useful — if empty — bulletin).
    try:
        nums = await asyncio.wait_for(asyncio.to_thread(_collect_numbers), timeout=10.0)
    except Exception as e:
        logger.warning(f"[office_briefing] collect timed out/failed (10s budget): {e}")
        nums = {"overdue_jobs": 0, "failed_jobs": 0, "dlq_depth": 0, "hot_queue": 0,
                "new_leads": 0, "qualified_leads": 0, "top_agents": []}
    try:
        text = await _compose_text(nums)
    except Exception as e:
        logger.warning(f"[office_briefing] compose failed: {e}")
        return {"ok": False, "date": date, "text": "", "has_audio": False,
                "error": "briefing compose fail"}

    has_audio = False
    try:
        has_audio = bool(await _tts_to_file(text, mpath))
    except Exception as e:
        logger.debug(f"[office_briefing] TTS failed -> text-only: {e}")
        has_audio = False
        try:
            if os.path.exists(mpath):
                os.remove(mpath)  # never leave a half-written mp3
        except Exception:
            pass

    try:
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump({"date": date, "text": text, "generated_at": _now_iso()}, f, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"[office_briefing] cache write skipped: {e}")

    return {"ok": True, "date": date, "text": text, "has_audio": has_audio, "cached": False}


def audio_path_for_today() -> str | None:
    """Path to today's cached mp3 if it exists, else None (endpoint 404-safe)."""
    try:
        p = _mp3_path(_ist_date())
        return p if os.path.exists(p) else None
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
