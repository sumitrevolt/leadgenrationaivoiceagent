"""Live Notes — Rowboat-style auto-updating notes on topics (compounding research).

User/agent ek TOPIC register karta (e.g. "solar Pune", "gym offers") → roz ek
dated "aaj ka update" section us topic ke markdown me APPEND hota:
trends (Google Trends RSS reuse) + optional weather angle (city ho to) +
free-LLM 1-para Hinglish digest. Content/sales agents in notes ko padh ke
fresh angle uthate.

Files: data/memory/topics/<slug>.md (memory_vault ka topics dir — format yahan
dated `## YYYY-MM-DD` sections, latest TOP; cap 40KB, purane trim).
Registry: data/live_topics.jsonl. Gated `LIVE_NOTES=1` (default OFF).
Max 5 topics/run, 1 refresh/topic/day. Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_TOPICS_FILE = os.path.join("data", "live_topics.jsonl")
_MAX_NOTE_BYTES = 40 * 1024
_MAX_PER_RUN = 5
_IST = timezone(timedelta(hours=5, minutes=30))


def _today() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip()).strip("-").lower()
    return s[:60] or "topic"


def _note_path(slug: str) -> str:
    from app.platform import memory_vault

    return os.path.join(memory_vault._MEM_DIR, "topics", slugify(slug) + ".md")


# --------------------------------------------------------------------------- #
# Topic registry
# --------------------------------------------------------------------------- #
def _read_topics() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if os.path.isfile(_TOPICS_FILE):
            with open(_TOPICS_FILE, encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                        if isinstance(r, dict):
                            out.append(r)
                    except Exception:
                        continue
    except Exception as e:
        logger.debug(f"[notes] topics read failed: {e}")
    return out


def _write_topics(rows: list[dict[str, Any]]) -> bool:
    try:
        os.makedirs(os.path.dirname(_TOPICS_FILE) or ".", exist_ok=True)
        tmp = _TOPICS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, _TOPICS_FILE)
        return True
    except Exception as e:
        logger.warning(f"[notes] topics write failed: {e}")
        return False


def add_topic(topic: str, niche: str = "", city: str = "") -> dict[str, Any]:
    """Naya live-note topic (slug-dedupe). Kabhi raise nahi."""
    try:
        t = str(topic or "").strip()[:120]
        if not t:
            return {"ok": False, "error": "topic chahiye"}
        slug = slugify(t)
        rows = _read_topics()
        for r in rows:
            if slugify(r.get("topic", "")) == slug:
                return {"ok": True, "topic": r, "existing": True}
        rec = {
            "id": uuid.uuid4().hex[:10],
            "topic": t,
            "niche": str(niche or "").strip()[:60],
            "city": str(city or "").strip()[:60],
            "created": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(rec)
        _write_topics(rows)
        return {"ok": True, "topic": rec, "existing": False}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_topics() -> list[dict[str, Any]]:
    rows = _read_topics()
    for r in rows:
        r["slug"] = slugify(r.get("topic", ""))
        try:
            p = _note_path(r["slug"])
            r["has_note"] = os.path.isfile(p)
            r["note_size"] = os.path.getsize(p) if r["has_note"] else 0
        except Exception:
            r["has_note"] = False
    return rows


def remove_topic(topic_id: str) -> dict[str, Any]:
    try:
        rows = _read_topics()
        keep = [r for r in rows if r.get("id") != topic_id]
        if len(keep) == len(rows):
            return {"ok": False, "error": "topic id nahi mila"}
        _write_topics(keep)
        return {"ok": True, "removed": topic_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# Refresh
# --------------------------------------------------------------------------- #
def _refreshed_today(slug: str) -> bool:
    try:
        p = _note_path(slug)
        if not os.path.isfile(p):
            return False
        with open(p, encoding="utf-8") as f:
            head = f.read(4096)
        return f"## {_today()}" in head
    except Exception:
        return False


def _append_section(slug: str, title_line: str, body: str) -> bool:
    """Dated section ko file TOP pe (header ke neeche) insert; 40KB cap pe purane
    sections trim. Kabhi raise nahi."""
    try:
        p = _note_path(slug)
        old = ""
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                old = f.read(_MAX_NOTE_BYTES + 8192)
        # header (pehli `# ` line) alag karo
        header = f"# {title_line}"
        rest = old
        if old.startswith("# "):
            nl = old.find("\n")
            header = old[: nl if nl != -1 else len(old)]
            rest = old[nl + 1 :] if nl != -1 else ""
        section = f"\n## {_today()}\n{body.strip()}\n"
        text = header + "\n" + section + rest.lstrip("\n")
        # 40KB cap — purane (last) sections drop
        while len(text.encode("utf-8")) > _MAX_NOTE_BYTES:
            cut = text.rfind("\n## ")
            if cut <= 0:
                text = text.encode("utf-8")[:_MAX_NOTE_BYTES].decode("utf-8", "ignore")
                break
            text = text[:cut].rstrip() + "\n"
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception as e:
        logger.warning(f"[notes] append failed {slug}: {e}")
        return False


async def refresh_topic(t: dict[str, Any]) -> dict[str, Any]:
    """Ek topic ka aaj ka update likho (trends + weather + LLM para). Kabhi raise nahi."""
    try:
        import asyncio

        topic = str(t.get("topic") or "").strip()
        if not topic:
            return {"ok": False, "error": "topic khali"}
        slug = slugify(topic)
        niche = str(t.get("niche") or "").strip()
        city = str(t.get("city") or "").strip()

        # 1) trends (reuse trends.py — free, no-key)
        angles: list[str] = []
        trending: list[str] = []
        try:
            from app.marketing import trends

            res = await asyncio.wait_for(
                trends.trend_angles(niche or topic, topic, n=3), timeout=25
            )
            angles = list(res.get("angles") or [])
            trending = list(res.get("trending") or [])[:5]
        except Exception as e:
            logger.debug(f"[notes] trends skip: {e}")

        # 2) weather angle (city ho to — Open-Meteo free)
        weather_line = ""
        if city:
            try:
                from app.marketing import weather_angle as _wa

                w = await asyncio.wait_for(_wa.weather_angle(city), timeout=10)
                if isinstance(w, dict) and w.get("ok"):
                    weather_line = (
                        f"Mausam ({city}): {w.get('angle') or w.get('season') or ''}".strip()
                    )
            except Exception as e:
                logger.debug(f"[notes] weather skip: {e}")

        # 3) free-LLM 1-para "aaj ka update" (fallback = angles join)
        para = ""
        provider = "fallback"
        try:
            from app.voice_agent import free_ai

            ctx = (
                f"Topic: {topic}. Niche: {niche or 'general'}. City: {city or '-'}. "
                f"Trending: {', '.join(trending) or '-'}. Angles: {' | '.join(angles) or '-'}. "
                f"{weather_line}"
            )
            para, provider = await asyncio.wait_for(
                free_ai.chat(
                    "Tum ek marketing research assistant ho. Diye gaye signals se topic ka AAJ KA "
                    "update ek SHORT Hinglish paragraph (3-4 line) me likho — kya chal raha, business "
                    "isse kaise fayda le. Sirf paragraph.",
                    [{"role": "user", "content": ctx}],
                    max_tokens=200,
                ),
                timeout=25,
            )
            para = (para or "").strip()
        except Exception as e:
            logger.debug(f"[notes] llm skip: {e}")
        if not para:
            para = "Aaj ke angles: " + (
                "; ".join(angles) if angles else "fresh content + seasonal offer push karo."
            )
            provider = "fallback"

        body_lines = [para]
        if weather_line:
            body_lines.append(f"- {weather_line}")
        for a in angles:
            body_lines.append(f"- Angle: {a}")
        if trending:
            body_lines.append(f"- Trending: {', '.join(trending)}")

        ok = _append_section(slug, topic, "\n".join(body_lines))
        return {"ok": ok, "slug": slug, "provider": provider, "angles": len(angles)}
    except Exception as e:
        logger.warning(f"[notes] refresh failed: {e}")
        return {"ok": False, "error": str(e)}


async def refresh_due(max_topics: int = _MAX_PER_RUN) -> dict[str, Any]:
    """Due topics refresh (1/topic/day dedupe, max 5/run). Kabhi raise nahi."""
    out: dict[str, Any] = {"ok": True, "refreshed": [], "skipped": 0}
    try:
        done = 0
        for t in _read_topics():
            if done >= max(1, max_topics):
                break
            slug = slugify(t.get("topic", ""))
            if _refreshed_today(slug):
                out["skipped"] += 1
                continue
            r = await refresh_topic(t)
            if r.get("ok"):
                out["refreshed"].append(slug)
            done += 1
    except Exception as e:
        out = {"ok": False, "error": str(e)}
    return out


def enabled() -> bool:
    return os.environ.get("LIVE_NOTES", "0").strip().lower() in ("1", "true", "yes")


async def refresh_if_enabled() -> dict[str, Any]:
    """Scheduler hook — gated LIVE_NOTES=1 (default OFF). Kabhi raise nahi."""
    if not enabled():
        return {"ok": False, "skipped": "LIVE_NOTES off"}
    return await refresh_due()


__all__ = [
    "slugify",
    "add_topic",
    "list_topics",
    "remove_topic",
    "refresh_topic",
    "refresh_due",
    "refresh_if_enabled",
    "enabled",
]
