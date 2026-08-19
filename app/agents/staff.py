"""
AI Staff workers — in-app jobs jo team roster ke naam se chalte hain.
=====================================================================

Har worker apna kaam karke `app.platform.team.log_event(...)` se record
karta hai (Team dashboard isi feed se "kaun kya kar raha" dikhata hai):

  - arjun (QA Engineer)  -> run_qa():      TelecallerBrain ko scripted convos
                                           se TEXT-mode me test karta (no WS,
                                           no phone — FREE), issues report.
  - meera (Trainer)      -> run_trainer(): data/call_transcripts/*.jsonl padh
                                           ke quality analysis + Hinglish
                                           tuning suggestions.
  - kavya (Ops Monitor)  -> run_ops():     providers/DB/disk health snapshot.

Sab functions import-safe hain aur KABHI raise nahi karte — error pe
{"error": "..."} return hota hai (scheduler/API kabhi nahi girte).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# QA conversation scripts (scripts/agent_tester.py ke SCRIPTS ka in-app copy —
# wahan WS drive hota hai, yahan brain.reply() DIRECT call hota hai).
# --------------------------------------------------------------------------- #
SCRIPTS: dict[str, list[str]] = {
    "solar_residential": [
        "haan boliye",
        "bijli ka bill bahut zyada aata hai",
        "lekin solar mehenga hota hai na",
        "abhi nahi baad me sochenge",
    ],
    "real_estate": [
        "haan",
        "2 BHK dhund raha hoon",
        "budget thoda kam hai",
        "site visit kab ho sakta hai",
    ],
    "insurance": [
        "haan bolo",
        "health insurance chahiye",
        "premium kitna hoga",
        "abhi busy hoon",
    ],
}

# Unknown niche ke liye generic user turns (QA phir bhi chal sake).
_GENERIC_TURNS: list[str] = [
    "haan boliye",
    "thoda detail me batao",
    "price kitna hoga",
    "abhi busy hoon",
]

# agent_tester.py jaisi banned meta-phrases (phone par bura lagta hai).
BANNED: list[str] = [
    "maine pehle",
    "pehle hi poocha",
    "unclear",
    "maaf kij",
    "[echo",
    "(no response)",
]

_TOO_LONG_WORDS = 35
_SLOW_S = 9.0
_QA_DEFAULT_MAX_TURNS = 18
_QA_DEFAULT_REPLY_TIMEOUT_S = 15.0


def _qa_run_limits() -> tuple[int, float]:
    """Bound scheduled QA so one slow free-model/provider cannot exhaust Celery.

    Real-transcript replay can add up to three niches on top of the twelve
    scripted turns.  Keep the default run comfortably below the 540s worker
    soft limit while leaving an explicit, bounded operator tuning path.
    """

    try:
        max_turns = int(
            os.getenv("QA_MAX_TURNS", str(_QA_DEFAULT_MAX_TURNS)) or _QA_DEFAULT_MAX_TURNS
        )
    except (TypeError, ValueError):
        max_turns = _QA_DEFAULT_MAX_TURNS
    try:
        reply_timeout_s = float(
            os.getenv("QA_REPLY_TIMEOUT_S", str(_QA_DEFAULT_REPLY_TIMEOUT_S))
            or _QA_DEFAULT_REPLY_TIMEOUT_S
        )
    except (TypeError, ValueError):
        reply_timeout_s = _QA_DEFAULT_REPLY_TIMEOUT_S
    return max(1, min(max_turns, 30)), max(0.05, min(reply_timeout_s, 30.0))


async def _log_trainer_event_bounded(
    team: Any,
    action: str,
    detail: str,
    *,
    status: str = "ok",
    meta: dict[str, Any] | None = None,
) -> None:
    """Telemetry must never hold the trainer job hostage.

    ``team.log_event`` is intentionally sync for legacy callers, but it may
    touch DB/Redis/Obsidian. Trainer analysis is still useful when telemetry
    is degraded, so run the write off-loop and bound the caller's wait.
    """
    loop = asyncio.get_running_loop()
    done = asyncio.Event()

    def _write() -> None:
        try:
            team.log_event("meera", action, detail, status, meta)
        finally:
            try:
                loop.call_soon_threadsafe(done.set)
            except Exception:
                pass

    threading.Thread(target=_write, name="trainer-telemetry", daemon=True).start()
    try:
        await asyncio.wait_for(done.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("[staff] trainer telemetry timed out; analysis preserved")
    except Exception as e:
        logger.debug("[staff] trainer telemetry skipped: %s", e)


# --------------------------------------------------------------------------- #
# arjun — QA run (text mode, brain direct)
# --------------------------------------------------------------------------- #
def _staff_job_failed(job: str, err: str) -> None:
    """W1.14: staff job ne {"error":...} return kiya (raise nahi → record_run ise
    ok=True samajhta). Dedicated fail metric + ntfy alert. Best-effort, never-raise."""
    try:
        from app.platform import job_metrics

        job_metrics.record_error(job)
    except Exception:
        pass
    try:
        from app.platform import ops_alerts

        ops_alerts.alert_staff_failure(job, err)
    except Exception:
        pass


def _qa_default_niches() -> list[str]:
    """W2.2: QA niche set parametrized — env `QA_NICHES` (comma-sep) se override,
    warna SCRIPTS ke 3 default. Bina-script niche = `_GENERIC_TURNS` (already handled),
    to koi bhi niche testable. Additive: QA_NICHES unset = purana 3-niche default."""
    raw = os.getenv("QA_NICHES", "").strip()
    if raw:
        got = [n.strip() for n in raw.split(",") if n.strip()]
        if got:
            return got
    return list(SCRIPTS.keys())


def _real_transcript_turns(max_per_niche: int = 6, files_n: int = 2) -> dict[str, list[str]]:
    """W2.2-half2: recent REAL call transcripts (data/call_transcripts/*.jsonl) se
    per-niche USER turns — QA canned scripts ke bajaye asli utterances (Hinglish-STT
    quirks samet) replay kar sake (run_qa me gated QA_REAL_TRANSCRIPTS). Junk-STT
    skip + dedupe + bounded. Never-raise → {}."""
    out: dict[str, list[str]] = {}
    try:
        d = str(_TRANSCRIPTS_DIR())
        try:
            files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl")]
        except Exception:
            return {}
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for path in files[:files_n]:
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        niche = str(rec.get("niche") or "general").strip() or "general"
                        turns = out.setdefault(niche, [])
                        for m in rec.get("messages") or []:
                            if (m.get("role") or "").lower() != "user":
                                continue
                            t = str(m.get("content") or "").strip()
                            if not t or _is_junk_stt(t) or t in turns:
                                continue
                            if len(turns) < max_per_niche:
                                turns.append(t)
            except Exception:
                continue
    except Exception:
        return {}
    return {k: v for k, v in out.items() if v}


async def run_qa(niches: list[str] | None = None) -> dict[str, Any]:
    """Scripted convos se TelecallerBrain ko test karo; issues collect + log.

    Checks (per turn): EMPTY reply, REPEAT (same as last), TOO-LONG (>35w),
    BANNED meta-phrase, SLOW (>9s). Returns {"issues": [...], "turns": N}.
    """
    from app.platform import team

    try:
        from app.voice_agent.telecaller_brain import TelecallerBrain

        targets = [n for n in (niches or _qa_default_niches()) if n]
        # W2.2-half2 (gated, default OFF = inert): real transcript user-turns replay
        # + transcript ke niches QA targets me (bounded +3) — QA wahi test kare jo
        # asli calls pe hota hai.
        real_turns: dict[str, list[str]] = {}
        if os.getenv("QA_REAL_TRANSCRIPTS", "").strip().lower() in ("1", "true", "yes", "on"):
            real_turns = _real_transcript_turns()
            targets = targets + [n for n in real_turns if n not in targets][:3]
        issues: list[str] = []
        total_turns = 0
        max_turns, reply_timeout_s = _qa_run_limits()
        truncated = False

        for niche_index, niche in enumerate(targets):
            turns = real_turns.get(niche) or SCRIPTS.get(niche, _GENERIC_TURNS)
            try:
                brain = TelecallerBrain(niche=niche)
                history: list[dict[str, str]] = []
                last_reply = ""
                for turn_index, turn in enumerate(turns):
                    if total_turns >= max_turns:
                        truncated = True
                        break
                    total_turns += 1
                    t0 = time.monotonic()
                    try:
                        reply = (
                            await asyncio.wait_for(
                                brain.reply(history, turn), timeout=reply_timeout_s
                            )
                            or ""
                        ).strip()
                    except asyncio.TimeoutError:
                        issues.append(
                            f"[{niche}] REPLY TIMEOUT after {reply_timeout_s:.1f}s for: {turn!r}"
                        )
                        reply = ""
                    except Exception as e:
                        issues.append(f"[{niche}] BRAIN ERROR for {turn!r}: {e}")
                        reply = ""
                    dt = time.monotonic() - t0

                    # ---- checks (agent_tester.py jaise) ----
                    if not reply:
                        issues.append(f"[{niche}] EMPTY reply for: {turn!r}")
                    low = reply.lower()
                    for b in BANNED:
                        if b in low:
                            issues.append(f"[{niche}] BANNED phrase '{b}' in: {reply!r}")
                    if reply and reply == last_reply:
                        issues.append(f"[{niche}] REPEAT reply: {reply!r}")
                    if len(reply.split()) > _TOO_LONG_WORDS:
                        issues.append(f"[{niche}] TOO LONG ({len(reply.split())}w): {reply!r}")
                    if dt > _SLOW_S:
                        issues.append(f"[{niche}] SLOW {dt:.1f}s for {turn!r}")

                    history.append({"role": "user", "content": turn})
                    if reply:
                        history.append({"role": "assistant", "content": reply})
                        last_reply = reply
            except Exception as e:
                issues.append(f"[{niche}] TEST CRASHED: {e}")
            if total_turns >= max_turns:
                # Reaching the cap exactly on the final available turn is complete,
                # not truncated.  Preserve that distinction for the admin record.
                truncated = (
                    truncated or (turn_index + 1 < len(turns)) or (niche_index + 1 < len(targets))
                )
                break

        team.log_event(
            "arjun",
            "qa_run",
            f"{len(issues)} issues across {len(targets)} niches ({total_turns}/{max_turns} turns)",
            status="warn" if issues else "ok",
            meta={
                "issues": issues[:20],
                "niches": targets,
                "turns": total_turns,
                "max_turns": max_turns,
                "reply_timeout_s": reply_timeout_s,
                "truncated": truncated,
            },
        )
        return {
            "issues": issues,
            "turns": total_turns,
            "niches": targets,
            "max_turns": max_turns,
            "truncated": truncated,
        }
    except Exception as e:
        logger.warning(f"[staff] run_qa failed: {e}")
        try:
            team.log_event("arjun", "qa_run", f"QA crash: {e}", status="error")
        except Exception:
            pass
        _staff_job_failed("qa", str(e))  # W1.14: fail metric + ntfy alert
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# meera — trainer (transcript analysis)
# --------------------------------------------------------------------------- #
def _is_junk_stt(text: str) -> bool:
    """STT garbage heuristic — bahut chhota ya sirf punctuation."""
    t = (text or "").strip()
    if len(t) < 3:
        return True
    return not any(ch.isalnum() for ch in t)


def _trainer_thresholds() -> tuple[int, float, int]:
    """W2.3: trainer suggestion thresholds env-tunable (pehle hardcoded 2 / 0.3 / 28) —
    deployment apne call-profile ke hisaab se retune kar sake. Garbage env = default."""

    def _num(env: str, default, cast):
        try:
            raw = os.getenv(env, "").strip()
            return cast(raw) if raw else default
        except Exception:
            return default

    return (
        _num("TRAINER_REPEAT_MAX", 2, int),
        _num("TRAINER_JUNK_RATIO", 0.3, float),
        _num("TRAINER_REPLY_WORDS", 28, int),
    )


# W2.3-half2: per-niche signal ke liye minimum user-turns — 1-2 turn wali niche
# ka junk-ratio noise hota, us par targeted suggestion nahi banate.
_NICHE_MIN_TURNS = 3


async def run_trainer() -> dict[str, Any]:
    """Newest 2 transcript files (data/call_transcripts/*.jsonl) analyse karo:
    calls/turns/stt-providers/avg-reply-length/repeats/junk-ratio + 2-3 short
    Hinglish suggestions. Returns summary dict ({"calls": 0} agar kuch nahi)."""
    from app.platform import team

    try:
        out_dir = str(_TRANSCRIPTS_DIR())
        files: list[str] = []
        try:
            files = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".jsonl")]
        except Exception:
            files = []
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        files = files[:2]

        if not files:
            await _log_trainer_event_bounded(
                team,
                "training_analysis",
                "koi call transcript nahi mila — analyse karne ko kuch nahi",
            )
            return {"calls": 0}

        calls = 0
        total_turns = 0
        stt_counts: dict[str, int] = {}
        reply_word_counts: list[int] = []
        repeats = 0
        junk_user = 0
        user_msgs = 0
        # W2.3-half2: per-niche accumulation — aggregate ek noisy niche ko mask
        # kar deta tha (global junk threshold ke niche, ek niche 100% junk).
        niche_stats: dict[str, dict[str, Any]] = {}

        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        calls += 1
                        niche = str(rec.get("niche") or "general").strip() or "general"
                        ns = niche_stats.setdefault(
                            niche,
                            {
                                "calls": 0,
                                "user_msgs": 0,
                                "junk_user": 0,
                                "reply_words": [],
                                "repeats": 0,
                            },
                        )
                        ns["calls"] += 1
                        for k, v in (rec.get("stt_counts") or {}).items():
                            try:
                                stt_counts[k] = stt_counts.get(k, 0) + int(v)
                            except Exception:
                                pass
                        msgs = rec.get("messages") or []
                        total_turns += len(msgs)
                        last_bot = None
                        for m in msgs:
                            role = (m.get("role") or "").lower()
                            content = str(m.get("content") or "").strip()
                            if role == "user":
                                user_msgs += 1
                                ns["user_msgs"] += 1
                                if _is_junk_stt(content):
                                    junk_user += 1
                                    ns["junk_user"] += 1
                            else:  # assistant/bot
                                if content:
                                    reply_word_counts.append(len(content.split()))
                                    ns["reply_words"].append(len(content.split()))
                                    if last_bot is not None and content == last_bot:
                                        repeats += 1
                                        ns["repeats"] += 1
                                    last_bot = content
            except Exception as e:
                logger.debug(f"[staff] trainer: file {path} skip: {e}")

        avg_reply_len = (
            round(sum(reply_word_counts) / len(reply_word_counts), 1) if reply_word_counts else 0.0
        )
        junk_ratio = round(junk_user / user_msgs, 2) if user_msgs else 0.0

        by_niche: dict[str, dict[str, Any]] = {}
        for n, ns in niche_stats.items():
            rw = ns["reply_words"]
            by_niche[n] = {
                "calls": ns["calls"],
                "user_turns": ns["user_msgs"],
                "junk_stt_ratio": (
                    round(ns["junk_user"] / ns["user_msgs"], 2) if ns["user_msgs"] else 0.0
                ),
                "avg_reply_words": round(sum(rw) / len(rw), 1) if rw else 0.0,
                "repeats": ns["repeats"],
            }

        # ---- rule-based Hinglish suggestions (W2.3: env-tunable thresholds) ----
        _rep_max, _junk_max, _words_max = _trainer_thresholds()
        suggestions: list[str] = []
        if repeats > _rep_max:
            suggestions.append(
                "Bot replies repeat ho rahi hain — script fallback rotate ho raha hai, prompts vary karo ya flow aage badhao."
            )
        if junk_ratio > _junk_max:
            suggestions.append(
                f"STT junk zyada hai ({int(junk_ratio*100)}% user turns garbage) — VAD/SILENCE_MS tune karo, Groq STT key check karo."
            )
        if avg_reply_len > _words_max:
            suggestions.append(
                f"Replies lambi hain (avg {avg_reply_len} words) — brevity cap aur tight karo (target <=25w)."
            )
        groq_n = stt_counts.get("groq", 0)
        other_n = sum(v for k, v in stt_counts.items() if k != "groq")
        if other_n > groq_n and (groq_n + other_n) > 0:
            suggestions.append(
                "Groq STT primary nahi chal raha (fallback zyada use hua) — GROQ_API_KEY / quota check karo."
            )
        # W2.3-half2: aggregate ke piche chhupi noisy-STT niche flag karo — global
        # junk threshold ke NICHE ho tab bhi ek niche cross kar sakti hai (masked).
        if junk_ratio <= _junk_max and len(by_niche) >= 2:
            _sig = [(n, d) for n, d in by_niche.items() if d["user_turns"] >= _NICHE_MIN_TURNS]
            if _sig:
                worst_n, worst_d = max(_sig, key=lambda x: x[1]["junk_stt_ratio"])
                if worst_d["junk_stt_ratio"] > _junk_max:
                    suggestions.append(
                        f"Niche '{worst_n}' me STT junk {int(worst_d['junk_stt_ratio'] * 100)}% hai "
                        "(baaki niches theek) — us niche ke calls/VAD/mic-path check karo."
                    )
        if not suggestions:
            suggestions.append(
                "Calls healthy lag rahi hain — koi major issue nahi, aise hi monitor karte raho."
            )
        suggestions = suggestions[:3]

        summary: dict[str, Any] = {
            "calls": calls,
            "turns": total_turns,
            "stt_counts": stt_counts,
            "avg_reply_words": avg_reply_len,
            "repeats": repeats,
            "junk_stt_ratio": junk_ratio,
            "by_niche": by_niche,
            "files": [os.path.basename(p) for p in files],
            "suggestions": suggestions,
        }
        await _log_trainer_event_bounded(
            team,
            "training_analysis",
            f"{calls} calls analysed, {len(suggestions)} suggestions",
            meta=summary,
        )
        # H3: persist suggestions to file so TelecallerBrain can inject them
        # into the system prompt on next call (closed learning loop).
        try:
            import json as _json
            import time as _time

            _hints_file = os.path.join("data", "trainer_suggestions.jsonl")
            # Keep CREATE identity as bare `data` (baseline fingerprint); the
            # dirname(_hints_file) form re-fingerprinted as new debt without
            # changing behaviour (2026-07-28 A4 ratchet).
            os.makedirs("data", exist_ok=True)
            with open(_hints_file, "a", encoding="utf-8") as _f:
                _f.write(
                    _json.dumps(
                        {"ts": int(_time.time()), "suggestions": suggestions},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass
        return summary
    except Exception as e:
        logger.warning(f"[staff] run_trainer failed: {e}")
        try:
            await _log_trainer_event_bounded(
                team, "training_analysis", f"trainer crash: {e}", status="error"
            )
        except Exception:
            pass
        _staff_job_failed("trainer", str(e))  # W1.14: fail metric + ntfy alert
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# kavya — ops health snapshot + data retention
# --------------------------------------------------------------------------- #
def _TRANSCRIPTS_DIR() -> str:
    """Call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return str(call_transcripts_dir())


_EVENT_RETENTION_DAYS = 60
_TRANSCRIPT_RETENTION_DAYS = 90

# W1.8: unbounded JSONL stores — append-only, koi prune nahi tha → disk unbounded grow.
# Line-cap rotation (newest rakho). Cap env-overridable; garbage env = default 20000.
try:
    _JSONL_MAX_LINES = max(1000, int(os.getenv("JSONL_ROTATE_MAX_LINES", "20000")))
except Exception:
    _JSONL_MAX_LINES = 20000
_JSONL_ROTATE_FILES = [
    os.path.join("data", "self_improve_runs.jsonl"),
    os.path.join("data", "content_feedback.jsonl"),
    os.path.join("data", "reply_drafts.jsonl"),
]


def _JSONL_ROTATE_DIR() -> str:
    """Per-tenant content queue dir — same store id as auto_content writers."""
    from pathlib import Path

    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="content.queue",
            legacy_path=Path("data") / "content_queue",
            target_segments=("content", "queue"),
        )
    )


def _prune_old_events(days: int = _EVENT_RETENTION_DAYS) -> int:
    """agent_events me `days` se purane rows delete karo (best-effort).

    Deleted count lautata hai; DB na ho ya kuch bhi fail ho to 0 — KABHI raise nahi.
    """
    try:
        from datetime import datetime, timedelta

        from app.models.agent_event import AgentEvent
        from app.platform import team

        db = team._db()
        if db is None:
            return 0
        try:
            cutoff = datetime.utcnow() - timedelta(days=max(1, int(days)))
            n = int(
                db.query(AgentEvent)
                .filter(AgentEvent.created_at < cutoff)
                .delete(synchronize_session=False)
                or 0
            )
            db.commit()
            return n
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[staff] event pruning skipped: {e}")
        return 0


def _prune_old_transcripts(days: int = _TRANSCRIPT_RETENTION_DAYS) -> int:
    """data/call_transcripts me `days` se purani files (mtime) delete karo.

    Removed count lautata hai; dir missing/locked files par bhi KABHI raise nahi.
    """
    removed = 0
    try:
        cutoff_ts = time.time() - max(1, int(days)) * 86400
        for fname in os.listdir(_TRANSCRIPTS_DIR()):
            fpath = os.path.join(_TRANSCRIPTS_DIR(), fname)
            try:
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff_ts:
                    os.remove(fpath)
                    removed += 1
            except Exception:
                continue  # ek file fail => baki phir bhi prune hon
    except Exception as e:
        logger.debug(f"[staff] transcript pruning skipped: {e}")
    return removed


def _trim_jsonl(target: str, max_lines: int = _JSONL_MAX_LINES) -> int:
    """W1.8: append-only JSONL ko last `max_lines` tak trim (newest rakho) — unbounded
    growth rok. Atomic tmp+os.replace, best-effort (site_beacon pattern). Removed count.

    Parameter is deliberately NOT named ``path``: a co-located
    ``path = .../inquiries`` Name plus the scanner's old Attribute.attr
    matching on ``os.path`` made ``os.replace(tmp, target)`` look like an
    inquiries writer (2026-07-28 A4). Scanner ``_refs`` is Name-only now;
    the rename stays as defense in depth.
    """
    try:
        if not os.path.isfile(target):
            return 0
        with open(target, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= max_lines:
            return 0
        keep = lines[-max_lines:]
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(keep)
        os.replace(tmp, target)
        return len(lines) - len(keep)
    except Exception as e:
        logger.debug(f"[staff] jsonl trim skipped ({target}): {e}")
        return 0


def _prune_jsonl_stores(max_lines: int = _JSONL_MAX_LINES) -> int:
    """W1.8: kavya hygiene — unbounded JSONL stores (self_improve_runs, content_feedback,
    reply_drafts, + content_queue/<id>.jsonl) ko cap pe trim. Total removed rows."""
    total = 0
    for _p in _JSONL_ROTATE_FILES:
        total += _trim_jsonl(_p, max_lines)
    try:
        # Probe then re-resolve at each I/O site — no local bind.
        _JSONL_ROTATE_DIR()
        if os.path.isdir(_JSONL_ROTATE_DIR()):
            for _fn in os.listdir(_JSONL_ROTATE_DIR()):
                if _fn.endswith(".jsonl"):
                    total += _trim_jsonl(os.path.join(_JSONL_ROTATE_DIR(), _fn), max_lines)
    except Exception as e:
        from app.platform import runtime_data as _rd

        if isinstance(e, _rd.RuntimeDataError):
            logger.error("[staff] content.queue authority UNRESOLVABLE: %s", e)
        else:
            logger.debug(f"[staff] content_queue prune skipped: {e}")
    return total


async def run_ops() -> dict[str, Any]:
    """Health snapshot: free-AI provider flags + DB reachability + disk free %.
    status="warn" agar koi provider off, DB down ya disk <10% free.
    Saath me data retention (best-effort): agent_events >60 din delete,
    call transcripts >90 din delete — pruned counts result me."""
    from app.platform import team

    try:
        # AI providers
        providers: dict[str, bool] = {}
        try:
            from app.voice_agent import free_ai

            providers = dict((free_ai.describe() or {}).get("providers") or {})
        except Exception as e:
            logger.debug(f"[staff] ops: free_ai describe failed: {e}")

        # DB reachable?
        db_ok = False
        try:
            db = team._db()
            db_ok = db is not None
            if db is not None:
                db.close()
        except Exception:
            db_ok = False

        # Disk free %
        disk_free_pct = -1.0
        try:
            du = shutil.disk_usage("/")
            if du.total:
                disk_free_pct = round(du.free / du.total * 100.0, 1)
        except Exception:
            pass

        # Data retention (best-effort pruning — har piece apne andar guarded)
        pruned_events = _prune_old_events()
        pruned_transcripts = _prune_old_transcripts()
        pruned_jsonl = _prune_jsonl_stores()  # W1.8: unbounded JSONL rotation
        try:  # W4.1: warm-lead SLA founder nudge (gated WARM_SLA_NUDGE, inert default)
            from app.platform import office_hq as _ohq

            await _ohq.warm_lead_sla_nudge()
        except Exception:
            pass

        providers_on = sum(1 for v in providers.values() if v)
        warn = (
            (providers and providers_on < len(providers))
            or (0 <= disk_free_pct < 10.0)
            or not db_ok
        )
        status = "warn" if warn else "ok"
        disk_txt = f"{disk_free_pct:.0f}% free" if disk_free_pct >= 0 else "n/a"
        summary = (
            f"providers {providers_on}/{len(providers)} on, "
            f"db {'ok' if db_ok else 'DOWN'}, disk {disk_txt}"
        )
        if pruned_events or pruned_transcripts or pruned_jsonl:
            summary += (
                f", pruned {pruned_events} old events"
                f" + {pruned_transcripts} old transcripts"
                f" + {pruned_jsonl} jsonl rows"
            )

        result: dict[str, Any] = {
            "status": status,
            "providers": providers,
            "db_ok": db_ok,
            "disk_free_pct": disk_free_pct,
            "uptime": "n/a",
            "pruned_events_60d": pruned_events,
            "pruned_transcripts_90d": pruned_transcripts,
            "pruned_jsonl_rows": pruned_jsonl,
        }
        team.log_event("kavya", "health_check", summary, status=status, meta=result)
        return result
    except Exception as e:
        logger.warning(f"[staff] run_ops failed: {e}")
        try:
            team.log_event("kavya", "health_check", f"ops crash: {e}", status="error")
        except Exception:
            pass
        _staff_job_failed("ops", str(e))  # W1.14: fail metric + ntfy alert
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# manager — daily digest (subah 08:30 IST scheduler se; on-demand bhi)
# --------------------------------------------------------------------------- #
def _count_recent_inquiries(hours: float = 24.0) -> int:
    """data/inquiries.jsonl me last-`hours` ki entries count karo (parse-safe)."""
    from datetime import datetime, timedelta

    count = 0
    # Keep the historical `path = ...` binding so the READ fingerprint stays in
    # the debt baseline. `_trim_jsonl`'s destination param is named `target`
    # so this symbol can no longer attach to os.replace (2026-07-28 A4).
    path = os.path.join("data", "inquiries.jsonl")
    try:
        if not os.path.isfile(path):
            return 0
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    at = str(rec.get("at") or "").replace("Z", "")
                    if at and datetime.fromisoformat(at) >= cutoff:
                        count += 1
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[staff] digest: inquiries count failed: {e}")
    return count


async def run_digest() -> dict[str, Any]:
    """Roz subah ka 4-5 line Hinglish digest: last-24h inquiries + ready
    prospects + Arjun ke recent QA issues + AI-provider health. Text
    data/daily_digest.txt me likhta hai, manager event log hota hai, aur
    NOTIFY_EMAIL configured ho to best-effort email bhi. KABHI raise nahi."""
    from datetime import datetime, timedelta

    from app.platform import team

    try:
        # 1) Inquiries (last 24h, jsonl)
        inquiries_24h = _count_recent_inquiries(24.0)

        # 2) Prospects ready (outreach queue)
        prospects_ready = 0
        try:
            from app.platform import prospector

            prospects_ready = len(prospector.list_prospects(status="ready", limit=500))
        except Exception as e:
            logger.debug(f"[staff] digest: prospects count failed: {e}")

        # 3) Recent QA issues (arjun ke warn/error events, last 24h)
        qa_issues = 0
        try:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            for ev in team.recent_events(limit=50, member="arjun"):
                if (ev.get("status") or "ok") not in ("warn", "error"):
                    continue
                try:
                    at = datetime.fromisoformat(str(ev.get("at") or "")).replace(tzinfo=None)
                    if at >= cutoff:
                        qa_issues += 1
                except Exception:
                    qa_issues += 1  # timestamp parse fail — count it anyway
        except Exception as e:
            logger.debug(f"[staff] digest: qa events failed: {e}")

        # 4) Health snapshot (free-AI provider flags)
        providers: dict[str, bool] = {}
        try:
            from app.voice_agent import free_ai

            providers = dict((free_ai.describe() or {}).get("providers") or {})
        except Exception as e:
            logger.debug(f"[staff] digest: free_ai describe failed: {e}")
        providers_on = sum(1 for v in providers.values() if v)

        # ---- 4-5 line Hinglish digest text ----
        today = datetime.now().strftime("%d-%m-%Y")
        lines = [
            f"📊 LeadGen AI — Daily Digest ({today})",
            f"1) Inquiries (24h): {inquiries_24h} nayi inquiry aayi"
            + ("" if inquiries_24h else " — landing/WhatsApp push badhao"),
            f"2) Outreach: {prospects_ready} prospects ready hain — aaj pitch bhejo",
            f"3) QA: {qa_issues} issue events (Arjun, 24h)"
            + (" — transcripts check karo" if qa_issues else " — voice agent healthy"),
            f"4) AI providers: {providers_on}/{len(providers) or 0} on"
            + ("" if providers and providers_on == len(providers) else " — keys/quota check karo"),
        ]
        text = "\n".join(lines)

        # ---- W2.4: optional cheap-LLM synthesis (why + next action) — gated DIGEST_LLM
        # (default OFF → pure rule-based). Free bulk profile (W1.10 cached). Fail-open. ----
        try:
            if os.getenv("DIGEST_LLM", "").strip().lower() in ("1", "true", "yes", "on"):
                from app.voice_agent import free_ai

                _synth, _ = await free_ai.chat(
                    system=(
                        "Tu ek SaaS founder ka short ops-analyst hai. Neeche aaj ke daily "
                        "metrics hain. SIRF 2 chhoti Hinglish lines de: (1) sabse bada 'why' "
                        "(kis cheez pe dhyan), (2) aaj ka #1 next action. Koi preamble nahi."
                    ),
                    messages=[{"role": "user", "content": text}],
                    max_tokens=120,
                    temperature=0.4,
                    scope="digest",
                    profile="bulk",
                )
                _synth = (_synth or "").strip()
                if _synth:
                    text = f"{text}\n\n🧠 {_synth}"
        except Exception as e:
            logger.debug(f"[staff] digest: LLM synth skipped: {e}")

        # ---- persist to data/daily_digest.txt (best-effort) ----
        try:
            os.makedirs(os.path.dirname(os.path.join("data", "daily_digest.txt")), exist_ok=True)
            with open(os.path.join("data", "daily_digest.txt"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception as e:
            logger.debug(f"[staff] digest: file write failed: {e}")

        summary: dict[str, Any] = {
            "text": text,
            "inquiries_24h": inquiries_24h,
            "prospects_ready": prospects_ready,
            "qa_issues_24h": qa_issues,
            "providers": providers,
        }
        team.log_event("manager", "daily_digest", text[:200], meta=summary)

        # ---- best-effort email (same notify path as inquiries) ----
        try:
            from app.config import settings

            to = (getattr(settings, "notify_email", "") or "").strip()
            if to and settings.smtp_user and settings.smtp_password:
                from app.integrations.email_sender import EmailSender

                await EmailSender().send_email([to], f"📊 LeadGen AI daily digest — {today}", text)
        except Exception as e:
            logger.debug(f"[staff] digest: email skipped: {e}")

        # ---- W1.15: best-effort phone push (ntfy) — daily digest founder ke phone pe.
        # Gated DIGEST_NTFY (default OFF, additive/inert); ntfy khud config-gate karta.
        try:
            if os.getenv("DIGEST_NTFY", "").strip().lower() in ("1", "true", "yes", "on"):
                from app.integrations import ntfy as _ntfy_mod

                await _ntfy_mod.push(
                    f"📊 Daily Digest — {today}", text, priority="default", tags=["bar_chart"]
                )
        except Exception as e:
            logger.debug(f"[staff] digest: ntfy push skipped: {e}")

        return summary
    except Exception as e:
        logger.warning(f"[staff] run_digest failed: {e}")
        try:
            team.log_event("manager", "daily_digest", f"digest crash: {e}", status="error")
        except Exception:
            pass
        _staff_job_failed("digest", str(e))  # W1.14: fail metric + ntfy alert
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# OWNER BRIEF — daily autonomous morning ntfy push when blockers/exceptions found
# --------------------------------------------------------------------------- #
async def run_daily_owner_brief() -> dict[str, Any]:
    """Roz subah owner-brief build karo. Agar P0/P1 exceptions ya pending owner
    decisions ho to ntfy push karo. Gated DAILY_OWNER_BRIEF_NTFY (default OFF).
    KABHI raise nahi."""
    try:
        from app.api.owner_brief import _build_owner_brief

        brief = _build_owner_brief()
        status = brief.get("status", "green")
        exceptions = brief.get("exceptions") or []
        next_actions = brief.get("next_actions") or []
        revenue = brief.get("revenue") or {}
        automation = brief.get("automation") or {}
        customers = brief.get("customers") or {}

        # Classify: push only when P0/P1 exist OR status is not green
        p0 = sum(1 for e in exceptions if e.get("severity") == "p0")
        p1 = sum(1 for e in exceptions if e.get("severity") == "p1")
        push_urgent = p0 > 0 or p1 > 0
        push_always = os.getenv("DAILY_OWNER_BRIEF_NTFY", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
            "always",
        )
        if not push_urgent and not push_always:
            return {
                "ok": True,
                "status": status,
                "exceptions": len(exceptions),
                "ntfy": "skipped",
                "reason": "no_p0_p1_and_not_always",
            }

        # Build Hinglish ntfy message
        lines: list[str] = []
        lines.append(f"📊 Owner Brief — {status.upper()}")
        lines.append(
            f"MRR ₹{revenue.get('mrr', 0)} | Paid {revenue.get('paid_customers', 0)} | "
            f"Pending UPI {revenue.get('pending_payments', 0)}"
        )
        lines.append(
            f"Jobs {automation.get('jobs_ok', 0)}/{automation.get('jobs_total', 0)} ok | "
            f"Overdue {automation.get('jobs_overdue', 0)} | DLQ {automation.get('dlq_depth', 0)}"
        )
        lines.append(
            f"Customers: {customers.get('total', 0)} total | "
            f"{customers.get('at_risk', 0)} at-risk | "
            f"{customers.get('pending_approvals', 0)} approvals pending"
        )
        if exceptions:
            lines.append("")
            lines.append("🔴 Exceptions:")
            for e in exceptions[:5]:
                sev = (e.get("severity") or "?").upper()
                lines.append(f"  [{sev}] {e.get('label', '')}")
        if next_actions:
            lines.append("")
            lines.append("👉 Next:")
            for a in next_actions[:3]:
                lines.append(f"  P{a.get('priority', '?')}: {a.get('action', '')}")
        text = "\n".join(lines)

        # Persist to data/daily_owner_brief.txt (best-effort)
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/daily_owner_brief.txt", "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass

        # Log event
        try:
            from app.platform import team

            team.log_event(
                "manager",
                "daily_owner_brief",
                text[:200],
                meta={
                    "status": status,
                    "exceptions": len(exceptions),
                    "p0": p0,
                    "p1": p1,
                    "next_actions": len(next_actions),
                },
            )
        except Exception:
            pass

        # ntfy push (P0 = urgent, P1 = high, else = default)
        try:
            from app.integrations import ntfy as _ntfy_mod

            if _ntfy_mod.enabled():
                priority = "urgent" if p0 > 0 else "high"
                tags = ["rotating_light"] if p0 > 0 else ["memo", "chart_with_upwards_trend"]
                await _ntfy_mod.push(
                    f"🎯 Owner Brief — {status.upper()}",
                    text,
                    priority=priority,
                    tags=tags,
                )
                return {
                    "ok": True,
                    "status": status,
                    "exceptions": len(exceptions),
                    "ntfy": "pushed",
                    "p0": p0,
                    "p1": p1,
                }
        except Exception as e:
            logger.debug(f"[staff] daily_owner_brief: ntfy push failed: {e}")

        return {
            "ok": True,
            "status": status,
            "exceptions": len(exceptions),
            "ntfy": "disabled",
        }
    except Exception as e:
        logger.warning(f"[staff] run_daily_owner_brief failed: {e}")
        _staff_job_failed("daily_owner_brief", str(e))
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# isha — per-client auto social-media content (run_daily_content wrapper)
# --------------------------------------------------------------------------- #
async def run_content() -> dict[str, Any]:
    """Sab active marketing clients ke liye aaj ka social content generate karo
    (auto_content engine). Import-safe, KABHI raise nahi."""
    try:
        from app.marketing import auto_content

        return await auto_content.run_daily_content()
    except Exception as e:
        logger.warning(f"[staff] run_content failed: {e}")
        _staff_job_failed("content", str(e))  # W1.14 parity: fail metric + ntfy alert
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# isha — programmatic SEO blog (run_daily_blog wrapper)
# --------------------------------------------------------------------------- #
async def run_blog(n: int = 3) -> dict[str, Any]:
    """n naye niche×city SEO articles publish karo (/blog + sitemap me aate).
    Free LLM, template fallback. Import-safe, KABHI raise nahi."""
    try:
        from app.marketing import seo_blog

        return await seo_blog.run_daily_blog(n)
    except Exception as e:
        logger.warning(f"[staff] run_blog failed: {e}")
        _staff_job_failed("blog", str(e))  # W1.14 parity: fail metric + ntfy alert
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# rohan — automated email outreach (run_email_outreach wrapper)
# --------------------------------------------------------------------------- #
async def run_email_outreach() -> dict[str, Any]:
    """Ready prospects ko auto cold email bhejo (auto_outreach engine).
    Flag/SMTP off ho to skip. Import-safe, KABHI raise nahi."""
    try:
        from app.platform import auto_outreach

        return await auto_outreach.run_email_outreach()
    except Exception as e:
        logger.warning(f"[staff] run_email_outreach failed: {e}")
        _staff_job_failed("email_outreach", str(e))  # W1.14 parity: fail metric + ntfy alert
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# manager — growth pulse (self-run/self-improve tick; har 15 min scheduler se)
# --------------------------------------------------------------------------- #
async def run_growth() -> dict[str, Any]:
    """Growth-engine pulse — metrics + pipeline self-heal + pitch-learning.
    Import-safe, KABHI raise nahi karta."""
    try:
        from app.platform import growth_engine

        return await growth_engine.pulse()
    except Exception as e:
        logger.warning(f"[staff] run_growth failed: {e}")
        _staff_job_failed("growth", str(e))  # W1.14 parity: fail metric + ntfy alert
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# Extended run_* wrappers — 25 previously non-runnable agents ko manual-trigger
# surface dete hain. Har wrapper apne engine ko delegate karta hai, env-flag
# check karta hai, aur KABHI raise nahi karta. Log via team.log_event().
# Pattern: try/import → flag check → engine call → log → result dict.
# --------------------------------------------------------------------------- #


def _flag_on(flag: str) -> bool:
    """Env flag active hai ya nahi — util for gated agents."""
    return (os.environ.get(flag) or "").strip().lower() in ("1", "true", "yes")


def _log(member: str, action: str, detail: str, status: str = "ok") -> None:
    """Safe team.log_event wrapper — never raises."""
    try:
        from app.platform import team

        team.log_event(member, action, detail, status=status)
    except Exception:
        pass


def _track_agent_cost(agent_id: str, result: dict[str, Any], elapsed_s: float) -> None:
    """Best-effort per-agent cost tracking via agent_cost_tracker. Never raises."""
    try:
        from app.platform import agent_cost_tracker as act

        # Extract provider/token info if the run result contains it
        provider = result.get("provider", "") or ""
        tokens_in = int(result.get("cost_tokens_in", 0) or result.get("tokens_in", 0) or 0)
        tokens_out = int(result.get("cost_tokens_out", 0) or result.get("tokens_out", 0) or 0)
        act.record(
            agent_id, provider=provider or "unknown", tokens_in=tokens_in, tokens_out=tokens_out
        )
    except Exception:
        pass


async def run_swara() -> dict[str, Any]:
    """Swara (Voice Agent) — readiness status check. On-demand voice actor,
    no standalone batch — reports voice subsystem health."""
    try:
        from app.voice_agent import free_ai

        providers = await free_ai.provider_status() if hasattr(free_ai, "provider_status") else {}
        _log("swara", "readiness_check", f"Voice subsystem: {len(providers)} providers")
        return {"ok": True, "type": "readiness", "providers": providers}
    except Exception as e:
        _log("swara", "readiness_check", str(e), "error")
        return {"error": str(e)}


async def run_ananya() -> dict[str, Any]:
    """Ananya (Booking Campaigns) — booking reminders + callback queue."""
    try:
        from app.platform import booking_reminders

        res = await booking_reminders.run_due()
        _log("ananya", "booking_reminders", f"Reminders: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("ananya", "booking_reminders", str(e), "error")
        return {"error": str(e)}


async def run_riya() -> dict[str, Any]:
    """Riya (Inbound/Widget) — readiness check. Event-driven agent."""
    try:
        _log("riya", "readiness_check", "Inbound widget agent ready")
        return {"ok": True, "type": "readiness", "detail": "event-driven, no batch run"}
    except Exception as e:
        return {"error": str(e)}


async def run_dev() -> dict[str, Any]:
    """Dev (New Client Setup) — onboarding sweep + ML training status."""
    try:
        from app.marketing import onboarding

        res = await onboarding.run_onboarding_sweep()
        _log("dev", "onboarding_sweep", f"Sweep: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("dev", "onboarding_sweep", str(e), "error")
        return {"error": str(e)}


async def run_lekha() -> dict[str, Any]:
    """Lekha (Call KPI Analyst) — daily call analytics digest."""
    try:
        from app.voice_agent import call_analytics

        call_analytics.run_daily_digest()
        _log("lekha", "call_kpi_digest", "KPI digest generated")
        return {"ok": True}
    except Exception as e:
        _log("lekha", "call_kpi_digest", str(e), "error")
        return {"error": str(e)}


async def run_raksha() -> dict[str, Any]:
    """Raksha (Live Call Monitor) — call transfer readiness (gated CALL_TRANSFER)."""
    try:
        if not _flag_on("CALL_TRANSFER"):
            return {"ok": True, "status": "flag_off:CALL_TRANSFER"}
        _log("raksha", "readiness_check", "Call transfer system ready")
        return {"ok": True, "type": "readiness"}
    except Exception as e:
        return {"error": str(e)}


async def run_hermes() -> dict[str, Any]:
    """Hermes (Infra Watchdog) — ops watchdog safety checks (gated INFRA_HANDLER)."""
    try:
        from app.platform import ops_watchdog

        res = ops_watchdog.run_checks()
        _log("hermes", "watchdog", f"Checks: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("hermes", "watchdog", str(e), "error")
        return {"error": str(e)}


async def run_tara() -> dict[str, Any]:
    """Tara (Voice Watchdog) — voice subsystem monitoring."""
    try:
        from app.platform import ops_watchdog

        res = ops_watchdog.run_checks()
        _log("tara", "voice_watchdog", f"Voice health: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("tara", "voice_watchdog", str(e), "error")
        return {"error": str(e)}


async def run_nikhil() -> dict[str, Any]:
    """Nikhil (Revenue Ops) — revenue digest + client health + usage alerts."""
    try:
        results = {}
        try:
            from app.platform import revenue_digest

            results["revenue"] = await revenue_digest.maybe_run_weekly()
        except Exception as e:
            results["revenue"] = {"error": str(e)}
        try:
            from app.platform import client_health

            results["client_health"] = await client_health.run_check()
        except Exception as e:
            results["client_health"] = {"error": str(e)}
        try:
            from app.billing import usage_alerts

            results["usage_alerts"] = await usage_alerts.run_check()
        except Exception as e:
            results["usage_alerts"] = {"error": str(e)}
        _log("nikhil", "revenue_ops", f"3 engines run: {list(results.keys())}")
        return {"ok": True, "results": results}
    except Exception as e:
        return {"error": str(e)}


async def run_vikram() -> dict[str, Any]:
    """Vikram (Code Upgrader) — code-upgrade proposals (gated CODE_UPGRADER)."""
    try:
        from app.agents import code_upgrader

        await code_upgrader.run_if_enabled()
        _log("vikram", "code_upgrader", "Code upgrade check complete")
        return {"ok": True}
    except Exception as e:
        _log("vikram", "code_upgrader", str(e), "error")
        return {"error": str(e)}


async def run_guru() -> dict[str, Any]:
    """Guru (Skill Pack) — skill KB ingest (gated SKILL_PACK)."""
    try:
        from app.platform import skill_pack

        if not skill_pack.enabled():
            return {"ok": True, "status": "flag_off:SKILL_PACK"}
        res = skill_pack.ingest_to_kb()
        _log("guru", "skill_ingest", f"Skills → KB: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("guru", "skill_ingest", str(e), "error")
        return {"error": str(e)}


async def run_pranav() -> dict[str, Any]:
    """Pranav (SRE) — reliability score (gated SRE_AGENT)."""
    try:
        from app.platform import engineer_agents

        res = engineer_agents.run_sre()
        _log("pranav", "sre_check", f"SRE: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("pranav", "sre_check", str(e), "error")
        return {"error": str(e)}


async def run_vidya() -> dict[str, Any]:
    """Vidya (FinOps) — margin digest (gated FINOPS_AGENT)."""
    try:
        from app.platform import engineer_agents

        res = engineer_agents.run_finops()
        _log("vidya", "finops_check", f"FinOps: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("vidya", "finops_check", str(e), "error")
        return {"error": str(e)}


async def run_arnav() -> dict[str, Any]:
    """Arnav (Security) — compliance posture (gated SECURITY_AGENT)."""
    try:
        from app.platform import engineer_agents

        res = engineer_agents.run_security()
        _log("arnav", "security_check", f"Security: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("arnav", "security_check", str(e), "error")
        return {"error": str(e)}


async def run_kabir() -> dict[str, Any]:
    """Kabir (DBRE) — Postgres reliability (gated DBRE_AGENT)."""
    try:
        from app.platform import engineer_agents

        res = engineer_agents.run_dbre()
        _log("kabir", "dbre_check", f"DBRE: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("kabir", "dbre_check", str(e), "error")
        return {"error": str(e)}


async def run_diya() -> dict[str, Any]:
    """Diya (Data Integrity) — lead/CRM data integrity (gated DATA_INTEGRITY_AGENT)."""
    try:
        from app.platform import engineer_agents

        res = engineer_agents.run_dataquality()
        _log("diya", "dataquality_check", f"Data quality: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("diya", "dataquality_check", str(e), "error")
        return {"error": str(e)}


async def run_aryan() -> dict[str, Any]:
    """Aryan (Deps Audit) — dependency CVE audit (gated DEPS_AGENT)."""
    try:
        from app.platform import engineer_agents

        res = engineer_agents.run_deps()
        _log("aryan", "deps_check", f"Deps: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("aryan", "deps_check", str(e), "error")
        return {"error": str(e)}


async def run_arya() -> dict[str, Any]:
    """Arya (MCP Engineer) — MCP health pulse (gated MCP_ENGINEER)."""
    try:
        from app.platform import mcp_engineer

        res = mcp_engineer.run_mcp()
        _log("arya", "mcp_check", f"MCP: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("arya", "mcp_check", str(e), "error")
        return {"error": str(e)}


async def run_ravi() -> dict[str, Any]:
    """Ravi (SEO/Blog) — programmatic SEO blog articles."""
    try:
        return await run_blog(n=3)
    except Exception as e:
        _log("ravi", "blog", str(e), "error")
        return {"error": str(e)}


async def run_neha() -> dict[str, Any]:
    """Neha (Pipeline Ops) — lead rescore + hot-lead surfacing."""
    try:
        from app.platform import pipeline_ops

        res = await pipeline_ops.run_daily()
        _log("neha", "pipeline", f"Pipeline: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("neha", "pipeline", str(e), "error")
        return {"error": str(e)}


async def run_kiran() -> dict[str, Any]:
    """Kiran (Campaign Optimizer) — campaign optimization (gated CAMPAIGN_OPTIMIZER)."""
    try:
        from app.agents import campaign_optimizer

        res = await campaign_optimizer.optimize()
        _log("kiran", "campaign_optimize", f"Optimizer: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("kiran", "campaign_optimize", str(e), "error")
        return {"error": str(e)}


async def run_priya() -> dict[str, Any]:
    """Priya (CRM Sync) — customer CRM sync + wishes (gated CRM_SYNC)."""
    try:
        if not _flag_on("CRM_SYNC"):
            return {"ok": True, "status": "flag_off:CRM_SYNC"}
        from app.marketing import customer_crm

        res = await customer_crm.run_wishes_if_enabled()
        _log("priya", "crm_sync", f"CRM: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("priya", "crm_sync", str(e), "error")
        return {"error": str(e)}


async def run_zara() -> dict[str, Any]:
    """Zara (Social Publisher) — social queue drain (gated SOCIAL_ENGINE)."""
    try:
        if not _flag_on("SOCIAL_ENGINE"):
            return {"ok": True, "status": "flag_off:SOCIAL_ENGINE"}
        from app.social_engine import engine as social_engine

        res = await social_engine.process_queue(30)
        _log("zara", "social_drain", f"Social: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("zara", "social_drain", str(e), "error")
        return {"error": str(e)}


async def run_anika() -> dict[str, Any]:
    """Anika (Cadence) — omnichannel cadence advance (gated CADENCE_ENGINE)."""
    try:
        if not _flag_on("CADENCE_ENGINE"):
            return {"ok": True, "status": "flag_off:CADENCE_ENGINE"}
        from app.marketing import cadence

        res = await cadence.run_due()
        _log("anika", "cadence", f"Cadence: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("anika", "cadence", str(e), "error")
        return {"error": str(e)}


async def run_ira() -> dict[str, Any]:
    """Ira (Journey/Hooks) — lifecycle nurture (gated JOURNEY_ENGINE)."""
    try:
        if not _flag_on("JOURNEY_ENGINE"):
            return {"ok": True, "status": "flag_off:JOURNEY_ENGINE"}
        from app.marketing import lifecycle_nurture

        res = await lifecycle_nurture.run_due()
        _log("ira", "lifecycle_nurture", f"Journey: {res}")
        return {"ok": True, "result": res}
    except Exception as e:
        _log("ira", "lifecycle_nurture", str(e), "error")
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# Dispatcher — member/job naam se sahi run_* function chalao (API + scheduler).
# --------------------------------------------------------------------------- #
async def run_member(member: str) -> dict[str, Any]:
    """Staff member ya job-name se kaam dispatch karo. Unknown -> {"error":...}.
    KABHI raise nahi karta.

    NOTE: this is the manual "Run now" path (called from app.api.team's
    `POST /run/{member}`) ONLY. team_scheduler.py's `_run_job_inner` calls the
    individual `run_qa()`/`run_ops()`/etc. functions DIRECTLY and never goes
    through this dispatcher — so the pause-check below cannot and does not
    affect scheduled/automatic runs, only this manual trigger."""
    key = (member or "").strip().lower()
    try:
        from app.platform import agent_controls

        if agent_controls.is_paused(key):
            logger.info(f"[staff] run_member({key}) skipped — paused by admin")
            try:
                from app.platform import team

                team.log_event(
                    key, "run_skipped_paused", "Manual run blocked — paused by admin", status="warn"
                )
            except Exception:
                pass
            return {"skipped": True, "reason": "paused_by_admin"}
    except Exception:
        pass

    # --- Paperclip budget governor: check before running ---
    try:
        from app.platform import agent_budget

        budget_result = agent_budget.check(key)
        if not budget_result.get("allowed", True):
            logger.info(
                f"[staff] run_member({key}) blocked — budget exceeded (tier {budget_result.get('tier')})"
            )
            try:
                from app.platform import team

                team.log_event(
                    key, "run_blocked_budget", f"Budget exceeded: {budget_result}", status="error"
                )
            except Exception:
                pass
            return {"skipped": True, "reason": "budget_exceeded", "budget": budget_result}
    except Exception:
        pass

    table = {
        # --- Original 6 RUNNABLE + aliases ---
        "arjun": run_qa,
        "qa": run_qa,
        "meera": run_trainer,
        "trainer": run_trainer,
        "kavya": run_ops,
        "ops": run_ops,
        "digest": run_digest,
        "manager": run_digest,
        "isha": run_content,
        "content": run_content,
        "blog": run_blog,
        "growth": run_growth,
        "rohan": run_email_outreach,
        "email_outreach": run_email_outreach,
        # --- Voice team ---
        "swara": run_swara,
        "ananya": run_ananya,
        "riya": run_riya,
        "lekha": run_lekha,
        "raksha": run_raksha,
        "tara": run_tara,
        # --- Marketing team ---
        "dev": run_dev,
        "ravi": run_ravi,
        "neha": run_neha,
        "kiran": run_kiran,
        "priya": run_priya,
        "zara": run_zara,
        "anika": run_anika,
        "ira": run_ira,
        # --- Platform / Engineering ---
        "hermes": run_hermes,
        "nikhil": run_nikhil,
        "vikram": run_vikram,
        "guru": run_guru,
        "pranav": run_pranav,
        "vidya": run_vidya,
        "arnav": run_arnav,
        "kabir": run_kabir,
        "diya": run_diya,
        "aryan": run_aryan,
        "arya": run_arya,
    }
    fn = table.get(key)
    if fn is None:
        return {"error": f"unknown member/job: {member}"}
    t0 = time.monotonic()
    try:
        result = await fn()
        _track_agent_cost(key, result, time.monotonic() - t0)
        # Harness shadow observation (record-only; Nikhil canary; INERT unless
        # AGENT_HARNESS+AGENT_HARNESS_SHADOW on and key in canary allowlist).
        # NEVER executes/blocks/retries the legacy run; never raises.
        try:
            from app.agents.harness.adapters import observe_legacy_run

            observe_legacy_run(
                key,
                action=f"staff.run_{key}",
                actual_result=result,
                latency_ms=int((time.monotonic() - t0) * 1000),
                source_loop="staff.run_member",
            )
        except Exception:
            pass
        return result
    except Exception as e:
        logger.warning(f"[staff] run_member({member}) failed: {e}")
        try:
            from app.agents.harness.adapters import observe_legacy_run

            observe_legacy_run(
                key,
                action=f"staff.run_{key}",
                actual_error=e,
                latency_ms=int((time.monotonic() - t0) * 1000),
                source_loop="staff.run_member",
            )
        except Exception:
            pass
        return {"error": str(e)}


__all__ = [
    "run_qa",
    "run_trainer",
    "run_ops",
    "run_digest",
    "run_content",
    "run_blog",
    "run_email_outreach",
    "run_growth",
    "run_member",
    # Extended roster — all 25 previously non-runnable agents
    "run_swara",
    "run_ananya",
    "run_riya",
    "run_dev",
    "run_lekha",
    "run_raksha",
    "run_hermes",
    "run_tara",
    "run_nikhil",
    "run_vikram",
    "run_guru",
    "run_pranav",
    "run_vidya",
    "run_arnav",
    "run_kabir",
    "run_diya",
    "run_aryan",
    "run_arya",
    "run_ravi",
    "run_neha",
    "run_kiran",
    "run_priya",
    "run_zara",
    "run_anika",
    "run_ira",
]
