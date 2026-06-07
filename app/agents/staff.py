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

import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# QA conversation scripts (scripts/agent_tester.py ke SCRIPTS ka in-app copy —
# wahan WS drive hota hai, yahan brain.reply() DIRECT call hota hai).
# --------------------------------------------------------------------------- #
SCRIPTS: Dict[str, List[str]] = {
    "solar_residential": [
        "haan boliye", "bijli ka bill bahut zyada aata hai",
        "lekin solar mehenga hota hai na", "abhi nahi baad me sochenge",
    ],
    "real_estate": [
        "haan", "2 BHK dhund raha hoon", "budget thoda kam hai",
        "site visit kab ho sakta hai",
    ],
    "insurance": [
        "haan bolo", "health insurance chahiye", "premium kitna hoga",
        "abhi busy hoon",
    ],
}

# Unknown niche ke liye generic user turns (QA phir bhi chal sake).
_GENERIC_TURNS: List[str] = [
    "haan boliye", "thoda detail me batao", "price kitna hoga", "abhi busy hoon",
]

# agent_tester.py jaisi banned meta-phrases (phone par bura lagta hai).
BANNED: List[str] = ["maine pehle", "pehle hi poocha", "unclear", "maaf kij", "[echo", "(no response)"]

_TOO_LONG_WORDS = 35
_SLOW_S = 9.0


# --------------------------------------------------------------------------- #
# arjun — QA run (text mode, brain direct)
# --------------------------------------------------------------------------- #
async def run_qa(niches: Optional[List[str]] = None) -> Dict[str, Any]:
    """Scripted convos se TelecallerBrain ko test karo; issues collect + log.

    Checks (per turn): EMPTY reply, REPEAT (same as last), TOO-LONG (>35w),
    BANNED meta-phrase, SLOW (>9s). Returns {"issues": [...], "turns": N}.
    """
    from app.platform import team

    try:
        from app.voice_agent.telecaller_brain import TelecallerBrain

        targets = [n for n in (niches or list(SCRIPTS.keys())) if n]
        issues: List[str] = []
        total_turns = 0

        for niche in targets:
            turns = SCRIPTS.get(niche, _GENERIC_TURNS)
            try:
                brain = TelecallerBrain(niche=niche)
                history: List[Dict[str, str]] = []
                last_reply = ""
                for turn in turns:
                    total_turns += 1
                    t0 = time.monotonic()
                    try:
                        reply = (await brain.reply(history, turn) or "").strip()
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

        team.log_event(
            "arjun",
            "qa_run",
            f"{len(issues)} issues across {len(targets)} niches ({total_turns} turns)",
            status="warn" if issues else "ok",
            meta={"issues": issues[:20], "niches": targets, "turns": total_turns},
        )
        return {"issues": issues, "turns": total_turns, "niches": targets}
    except Exception as e:
        logger.warning(f"[staff] run_qa failed: {e}")
        try:
            team.log_event("arjun", "qa_run", f"QA crash: {e}", status="error")
        except Exception:
            pass
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


async def run_trainer() -> Dict[str, Any]:
    """Newest 2 transcript files (data/call_transcripts/*.jsonl) analyse karo:
    calls/turns/stt-providers/avg-reply-length/repeats/junk-ratio + 2-3 short
    Hinglish suggestions. Returns summary dict ({"calls": 0} agar kuch nahi)."""
    from app.platform import team

    try:
        out_dir = os.path.join("data", "call_transcripts")
        files: List[str] = []
        try:
            files = [
                os.path.join(out_dir, f)
                for f in os.listdir(out_dir)
                if f.endswith(".jsonl")
            ]
        except Exception:
            files = []
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        files = files[:2]

        if not files:
            team.log_event("meera", "training_analysis",
                           "koi call transcript nahi mila — analyse karne ko kuch nahi")
            return {"calls": 0}

        calls = 0
        total_turns = 0
        stt_counts: Dict[str, int] = {}
        reply_word_counts: List[int] = []
        repeats = 0
        junk_user = 0
        user_msgs = 0

        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        calls += 1
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
                                if _is_junk_stt(content):
                                    junk_user += 1
                            else:  # assistant/bot
                                if content:
                                    reply_word_counts.append(len(content.split()))
                                    if last_bot is not None and content == last_bot:
                                        repeats += 1
                                    last_bot = content
            except Exception as e:
                logger.debug(f"[staff] trainer: file {path} skip: {e}")

        avg_reply_len = round(sum(reply_word_counts) / len(reply_word_counts), 1) if reply_word_counts else 0.0
        junk_ratio = round(junk_user / user_msgs, 2) if user_msgs else 0.0

        # ---- simple rule-based Hinglish suggestions ----
        suggestions: List[str] = []
        if repeats > 2:
            suggestions.append("Bot replies repeat ho rahi hain — script fallback rotate ho raha hai, prompts vary karo ya flow aage badhao.")
        if junk_ratio > 0.3:
            suggestions.append(f"STT junk zyada hai ({int(junk_ratio*100)}% user turns garbage) — VAD/SILENCE_MS tune karo, Groq STT key check karo.")
        if avg_reply_len > 28:
            suggestions.append(f"Replies lambi hain (avg {avg_reply_len} words) — brevity cap aur tight karo (target <=25w).")
        groq_n = stt_counts.get("groq", 0)
        other_n = sum(v for k, v in stt_counts.items() if k != "groq")
        if other_n > groq_n and (groq_n + other_n) > 0:
            suggestions.append("Groq STT primary nahi chal raha (fallback zyada use hua) — GROQ_API_KEY / quota check karo.")
        if not suggestions:
            suggestions.append("Calls healthy lag rahi hain — koi major issue nahi, aise hi monitor karte raho.")
        suggestions = suggestions[:3]

        summary: Dict[str, Any] = {
            "calls": calls,
            "turns": total_turns,
            "stt_counts": stt_counts,
            "avg_reply_words": avg_reply_len,
            "repeats": repeats,
            "junk_stt_ratio": junk_ratio,
            "files": [os.path.basename(p) for p in files],
            "suggestions": suggestions,
        }
        team.log_event(
            "meera",
            "training_analysis",
            f"{calls} calls analysed, {len(suggestions)} suggestions",
            meta=summary,
        )
        return summary
    except Exception as e:
        logger.warning(f"[staff] run_trainer failed: {e}")
        try:
            team.log_event("meera", "training_analysis", f"trainer crash: {e}", status="error")
        except Exception:
            pass
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# kavya — ops health snapshot
# --------------------------------------------------------------------------- #
async def run_ops() -> Dict[str, Any]:
    """Health snapshot: free-AI provider flags + DB reachability + disk free %.
    status="warn" agar koi provider off, DB down ya disk <10% free."""
    from app.platform import team

    try:
        # AI providers
        providers: Dict[str, bool] = {}
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

        result: Dict[str, Any] = {
            "status": status,
            "providers": providers,
            "db_ok": db_ok,
            "disk_free_pct": disk_free_pct,
            "uptime": "n/a",
        }
        team.log_event("kavya", "health_check", summary, status=status, meta=result)
        return result
    except Exception as e:
        logger.warning(f"[staff] run_ops failed: {e}")
        try:
            team.log_event("kavya", "health_check", f"ops crash: {e}", status="error")
        except Exception:
            pass
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# manager — daily digest (subah 08:30 IST scheduler se; on-demand bhi)
# --------------------------------------------------------------------------- #
def _count_recent_inquiries(hours: float = 24.0) -> int:
    """data/inquiries.jsonl me last-`hours` ki entries count karo (parse-safe)."""
    from datetime import datetime, timedelta

    count = 0
    path = os.path.join("data", "inquiries.jsonl")
    try:
        if not os.path.isfile(path):
            return 0
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with open(path, "r", encoding="utf-8") as f:
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


async def run_digest() -> Dict[str, Any]:
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
        providers: Dict[str, bool] = {}
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

        # ---- persist to data/daily_digest.txt (best-effort) ----
        try:
            os.makedirs("data", exist_ok=True)
            with open(os.path.join("data", "daily_digest.txt"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception as e:
            logger.debug(f"[staff] digest: file write failed: {e}")

        summary: Dict[str, Any] = {
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

                await EmailSender().send_email(
                    [to], f"📊 LeadGen AI daily digest — {today}", text
                )
        except Exception as e:
            logger.debug(f"[staff] digest: email skipped: {e}")

        return summary
    except Exception as e:
        logger.warning(f"[staff] run_digest failed: {e}")
        try:
            team.log_event("manager", "daily_digest", f"digest crash: {e}", status="error")
        except Exception:
            pass
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
async def run_member(key: str) -> Dict[str, Any]:
    """Staff member ka job manually chalao — arjun/meera/kavya/manager(digest)."""
    try:
        jobs = {
            "arjun": run_qa,
            "meera": run_trainer,
            "kavya": run_ops,
            "manager": run_digest,
            "digest": run_digest,
        }
        fn = jobs.get((key or "").strip().lower())
        if fn is None:
            return {"error": "unknown member"}
        return await fn()
    except Exception as e:
        return {"error": str(e)}


__all__ = ["SCRIPTS", "BANNED", "run_qa", "run_trainer", "run_ops", "run_digest", "run_member"]
