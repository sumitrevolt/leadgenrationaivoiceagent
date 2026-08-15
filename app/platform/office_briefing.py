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

# EdgeTTS has NO internal timeout (aiohttp default ~300s) — a stall would pin one
# of only WEB_CONCURRENCY=2 workers (documented prod-down class). Module-level so
# tests can shrink it.
_TTS_TIMEOUT_S = 20.0
_CLAIM_STALE_S = 120.0  # collect(10) + LLM(25) + TTS(20), with generous headroom
_CLAIM_WAIT_S = 60.0

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


def _claim_path(date: str) -> str:
    return os.path.join(_DIR, f"{date}.building")


def _read_cached(date: str) -> dict[str, Any] | None:
    try:
        jpath = _json_path(date)
        if not os.path.exists(jpath):
            return None
        with open(jpath, encoding="utf-8") as f:
            cached = json.load(f) or {}
        return {
            "ok": True,
            "date": date,
            "text": cached.get("text") or "",
            "has_audio": os.path.exists(_mp3_path(date)),
            "cached": True,
        }
    except Exception as exc:
        logger.debug("[office_briefing] cache read skipped: %s", exc)
        return None


def _try_generation_claim(date: str) -> bool:
    """Cross-process one-writer claim; stale claims recover after bounded work."""
    path = _claim_path(date)
    for _attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"pid={os.getpid()} at={_now_iso()}".encode())
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            try:
                if datetime.now(timezone.utc).timestamp() - os.path.getmtime(path) > _CLAIM_STALE_S:
                    os.remove(path)
                    continue
            except FileNotFoundError:
                continue
            except Exception:
                pass
            return False
        except Exception as exc:
            logger.warning("[office_briefing] generation claim failed: %s", exc)
            return False
    return False


def _release_generation_claim(date: str) -> None:
    try:
        os.remove(_claim_path(date))
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("[office_briefing] generation claim release failed: %s", exc)


async def _wait_for_cached(date: str) -> dict[str, Any] | None:
    deadline = asyncio.get_running_loop().time() + _CLAIM_WAIT_S
    while asyncio.get_running_loop().time() < deadline:
        cached = _read_cached(date)
        if cached is not None:
            return cached
        if not os.path.exists(_claim_path(date)):
            return None
        await asyncio.sleep(0.1)
    return None


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
    lines.append(
        f"Reception ke Hot Queue me {nums['hot_queue']} garam replies kaam ke liye pending hain."
    )
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
        cached = _read_cached(date)
        if cached is not None:
            return cached

    if not _try_generation_claim(date):
        cached = await _wait_for_cached(date)
        if cached is not None:
            return cached
        return {
            "ok": False,
            "date": date,
            "text": "",
            "has_audio": False,
            "error": "briefing generation already in progress",
        }

    # Another process may have finished between our first cache read and claim.
    if not force:
        cached = _read_cached(date)
        if cached is not None:
            _release_generation_claim(date)
            return cached

    # _collect_numbers is SYNC and touches the DB + every draft/agent-event —
    # run it OFF the event loop with a hard deadline (same rule + pattern as
    # office_hq._safe_collect_live_stats; blocking the loop = documented prod-down
    # class). On timeout/failure degrade to zeros so a slow store never hangs the
    # briefing (the template still renders a useful — if empty — bulletin).
    try:
        nums = await asyncio.wait_for(asyncio.to_thread(_collect_numbers), timeout=10.0)
    except Exception as e:
        logger.warning(f"[office_briefing] collect timed out/failed (10s budget): {e}")
        nums = {
            "overdue_jobs": 0,
            "failed_jobs": 0,
            "dlq_depth": 0,
            "hot_queue": 0,
            "new_leads": 0,
            "qualified_leads": 0,
            "top_agents": [],
        }
    try:
        text = await _compose_text(nums)
    except Exception as e:
        logger.warning(f"[office_briefing] compose failed: {e}")
        _release_generation_claim(date)
        return {
            "ok": False,
            "date": date,
            "text": "",
            "has_audio": False,
            "error": "briefing compose fail",
        }

    has_audio = False
    try:
        # Bounded — same pattern as web_call.py TTS calls (see _TTS_TIMEOUT_S note).
        has_audio = bool(await asyncio.wait_for(_tts_to_file(text, mpath), timeout=_TTS_TIMEOUT_S))
    except Exception as e:
        logger.debug(f"[office_briefing] TTS failed -> text-only: {e}")
        has_audio = False
        try:
            if os.path.exists(mpath):
                os.remove(mpath)  # never leave a half-written mp3
        except Exception:
            pass

    cache_written = False
    try:
        from app.utils.file_lock import locked_rewrite

        cache_written = locked_rewrite(
            jpath,
            json.dumps(
                {"date": date, "text": text, "generated_at": _now_iso()},
                ensure_ascii=False,
            ),
        )
    except Exception as e:
        logger.debug(f"[office_briefing] cache write skipped: {e}")

    if not cache_written:
        try:
            if os.path.exists(mpath):
                os.remove(mpath)
        except Exception:
            pass
        _release_generation_claim(date)
        return {
            "ok": False,
            "date": date,
            "text": text,
            "has_audio": False,
            "error": "briefing cache write failed",
        }

    _release_generation_claim(date)
    return {"ok": True, "date": date, "text": text, "has_audio": has_audio, "cached": False}


def _scheduler_health() -> dict[str, Any]:
    """Read the automation control-plane status for the scheduled path.

    Unknown health is deliberately unhealthy: the council-approved automation
    must never spend an LLM/TTS call while its scheduler/queue state is unsafe.
    """
    try:
        from app.platform import automation_health

        health = automation_health.health() or {"ok": False, "status": "unknown"}
        queue = health.get("queue") or {}
        queue_unknown = any(
            int(queue.get(name, -1)) < 0 for name in ("celery", "heavy", "dlq", "dead")
        )
        recent_failed = [
            str(row.get("job") or "?")
            for row in (health.get("jobs") or [])
            if row.get("status") == "last_failed" and row.get("job") != "hot_queue_brief"
        ]
        if queue_unknown or recent_failed:
            return {
                **health,
                "ok": False,
                "queue_unknown": queue_unknown,
                "recent_failed": recent_failed,
            }
        return health
    except Exception as exc:
        logger.warning("[office_briefing] scheduler health unavailable: %s", exc)
        return {"ok": False, "status": "unknown", "error": str(exc)[:160]}


def _log_scheduled_event(status: str, detail: str) -> None:
    """Best-effort admin evidence; never sends email, WhatsApp, or calls."""
    try:
        from app.platform import team

        team.log_event(
            "rohan",
            "hot_queue_brief",
            str(detail)[:300],
            status="ok" if status == "ok" else "warn",
        )
    except Exception:
        pass


def _notification_path(date: str) -> str:
    return os.path.join(_DIR, f"{date}.owner-notified")


def _try_notification_claim(date: str) -> bool:
    """At-most-once daily owner reminder claim across worker processes."""
    try:
        fd = os.open(_notification_path(date), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, f"claimed_at={_now_iso()}".encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception as exc:
        logger.warning("[office_briefing] owner notification claim failed: %s", exc)
        return False


def _release_notification_claim(date: str) -> None:
    try:
        os.remove(_notification_path(date))
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("[office_briefing] owner notification claim release failed: %s", exc)


async def _notify_owner_once(result: dict[str, Any]) -> dict[str, Any]:
    """Send one internal, draft-only action reminder; never contacts a prospect."""
    date = str(result.get("date") or _ist_date())
    if not _try_notification_claim(date):
        return {"sent": False, "skipped": "already_notified"}

    from app.integrations import ntfy

    base = (os.environ.get("PUBLIC_BASE_URL") or "https://leadsgenai.in").rstrip("/")
    text = " ".join(str(result.get("text") or "").split())[:900]
    message = text or "Aaj ka Hot Queue revenue brief ready hai."
    actions = [{"action": "view", "label": "Hot Queue kholo", "url": f"{base}/app/inbox"}]
    for attempt in range(2):
        sent = await ntfy.push(
            "Hot Queue action pending",
            message,
            priority="high",
            tags=["fire"],
            actions=actions,
        )
        if sent:
            return {"sent": True, "attempts": attempt + 1, "action": "/app/inbox"}
        if attempt == 0:
            await asyncio.sleep(0.2)

    _release_notification_claim(date)
    return {"sent": False, "attempts": 2, "skipped": "notify_failed"}


async def run_scheduled() -> dict[str, Any]:
    """Build today's draft-only revenue brief when the control plane is safe.

    The existing daily cache is the idempotency ledger. Health collection runs
    off-loop and is bounded; degraded/unknown health fails closed before any
    LLM or TTS work. The result stays inside Office HQ and `/app/inbox` remains
    the human-only action surface.
    """
    enabled = os.environ.get("HOT_QUEUE_BRIEF_DAILY", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not enabled:
        return {"ok": True, "enabled": False, "skipped": "disabled"}

    try:
        health = await asyncio.wait_for(asyncio.to_thread(_scheduler_health), timeout=5.0)
    except Exception as exc:
        health = {"ok": False, "status": "unknown", "error": str(exc)[:160]}

    if not health.get("ok"):
        overdue = ",".join(str(j) for j in (health.get("overdue") or [])[:8]) or "none"
        detail = (
            f"skipped: health={health.get('status') or 'unknown'} "
            f"overdue={overdue} queue_backlogged={bool(health.get('queue_backlogged'))}"
        )
        _log_scheduled_event("warn", detail)
        # ADR-109 ops fix (2026-07-16): intentional fail-closed SKIP is NOT a job
        # failure. Returning ok:False made Celery retry → dlq:dead → health stayed
        # degraded → brief skipped forever (death spiral). ok:True + skipped keeps
        # the gate (no LLM/TTS) without poisoning DLQ / dead-man status.
        return {
            "ok": True,
            "enabled": True,
            "skipped": "automation_unhealthy",
            "health_status": health.get("status") or "unknown",
        }

    result = await build_briefing(force=False)
    if not result.get("ok"):
        _log_scheduled_event("warn", f"generation_failed: {result.get('error') or 'unknown'}")
        return {**result, "enabled": True}

    notification = await _notify_owner_once(result)
    if notification.get("skipped") == "notify_failed":
        _log_scheduled_event("warn", "owner_notification_failed: retries=2 action=/app/inbox")
    _log_scheduled_event(
        "ok",
        f"ready: date={result.get('date') or _ist_date()} cached={bool(result.get('cached'))} "
        f"owner_notified={bool(notification.get('sent'))} action=/app/inbox",
    )
    return {**result, "enabled": True, "owner_notification": notification}


def audio_path_for_today() -> str | None:
    """Path to today's cached mp3 if it exists, else None (endpoint 404-safe)."""
    try:
        p = _mp3_path(_ist_date())
        return p if os.path.exists(p) else None
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
