"""brand_pulse.py — Brand24-lite brand/mention monitor (FREE sources only).

Business naam ke mentions: Google News RSS + Reddit search JSON (dono free,
no-key, polite UA + 10s timeout) → per-mention rule-sentiment (sentiment.py ka
_rule reuse — NO LLM in scan, prod-down lesson) → Hinglish digest + har
NEGATIVE mention ka deterministic reply-DRAFT (send KABHI nahi — ban-safe).

6-hr cache: data/brand_pulse_cache.jsonl (repeat scans network-free).
Weekly sweep `run_weekly_if_enabled()` GATED `BRAND_PULSE=1` (default OFF):
active clients scan → data/brand_pulse_runs.jsonl + team event. NEVER raises.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CACHE_FILE = os.path.join("data", "brand_pulse_cache.jsonl")
_RUNS_FILE = os.path.join("data", "brand_pulse_runs.jsonl")
_CACHE_TTL = 6 * 3600  # 6 hours
_UA = "Mozilla/5.0 (compatible; LeadsGenAI-pulse/1.0; +https://leadsgenai.in)"

_NEWS_URL = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
_REDDIT_URL = "https://www.reddit.com/search.json?q={q}&limit=10&sort=new"


def _now() -> float:
    return time.time()


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[brand_pulse] append skip: {e}")


def _read(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Source parsers (pure-python — tests inhe offline verify karte hain)
# --------------------------------------------------------------------------- #
def parse_news_rss(xml: str) -> list[dict[str, str]]:
    """Google News RSS items → [{source,title,url,snippet}] (regex, no xml dep)."""
    out: list[dict[str, str]] = []
    try:
        for it in re.findall(r"<item>(.*?)</item>", xml or "", re.S)[:10]:
            tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
            lm = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", it, re.S)
            dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
            title = (tm.group(1).strip() if tm else "")[:200]
            if not title:
                continue
            snippet = re.sub(r"<[^>]+>", " ", (dm.group(1) if dm else "")).strip()[:300]
            out.append(
                {
                    "source": "google_news",
                    "title": title,
                    "url": (lm.group(1).strip() if lm else "")[:500],
                    "snippet": snippet,
                }
            )
    except Exception as e:
        logger.debug(f"[brand_pulse] rss parse skip: {e}")
    return out


def parse_reddit_json(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Reddit search JSON → mentions list. Defensive on shape."""
    out: list[dict[str, str]] = []
    try:
        children = ((payload or {}).get("data") or {}).get("children") or []
        for ch in children[:10]:
            d = (ch or {}).get("data") or {}
            title = str(d.get("title") or "").strip()[:200]
            if not title:
                continue
            out.append(
                {
                    "source": "reddit",
                    "title": title,
                    "url": ("https://www.reddit.com" + str(d.get("permalink") or ""))[:500],
                    "snippet": str(d.get("selftext") or "").strip()[:300],
                }
            )
    except Exception as e:
        logger.debug(f"[brand_pulse] reddit parse skip: {e}")
    return out


async def _fetch_google_news(query: str) -> list[dict[str, str]]:
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True, headers={"User-Agent": _UA}
        ) as c:
            r = await c.get(_NEWS_URL.format(q=quote(query)))
            if r.status_code == 200:
                return parse_news_rss(r.text)
    except Exception as e:
        logger.debug(f"[brand_pulse] news fetch skip: {e}")
    return []


async def _fetch_reddit(query: str) -> list[dict[str, str]]:
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True, headers={"User-Agent": _UA}
        ) as c:
            r = await c.get(_REDDIT_URL.format(q=quote(query)))
            if r.status_code == 200:
                return parse_reddit_json(r.json())
    except Exception as e:
        logger.debug(f"[brand_pulse] reddit fetch skip: {e}")
    return []


# --------------------------------------------------------------------------- #
# Sentiment + drafts (rule-based — scan me LLM NAHI; public-path-safe)
# --------------------------------------------------------------------------- #
def _label(text: str) -> str:
    try:
        from app.marketing.sentiment import _rule

        return _rule(text)
    except Exception:
        return "neutral"


def _reply_draft(business: str, mention: dict[str, str]) -> str:
    return (
        f"Namaste! {business} ki team se — aapki baat humne dekhi "
        f'("{mention.get("title", "")[:80]}"). Hum sach me sudharna chahte hain; '
        "kya aap details share kar sakte hain? Hum personally resolve karenge. "
        "DM/call dono open hai — dhanyavaad ki aapne bataya. 🙏"
    )


def _summary(business: str, mentions: list[dict], breakdown: dict[str, int]) -> str:
    if not mentions:
        return f"{business}: pichhle scan me koi naya public mention nahi mila — sab shaant hai. 👍"
    neg = breakdown.get("negative", 0)
    pos = breakdown.get("positive", 0)
    line = f"{business}: {len(mentions)} mentions mile (👍{pos} / 👎{neg})."
    if neg:
        line += f" {neg} negative pe reply-draft taiyaar hai — 1-click review karke bhejo."
    else:
        line += " Koi negative nahi — positive momentum ko post me convert karo!"
    return line


# --------------------------------------------------------------------------- #
# scan — main entry (cached 6hr)
# --------------------------------------------------------------------------- #
def _cache_get(key: str) -> dict[str, Any] | None:
    try:
        best: dict[str, Any] | None = None
        for rec in _read(_CACHE_FILE):
            if rec.get("key") == key and (_now() - float(rec.get("ts", 0))) < _CACHE_TTL:
                best = rec
        return best.get("digest") if best else None
    except Exception:
        return None


async def scan(
    business_name: str, city: str | None = None, niche: str | None = None
) -> dict[str, Any]:
    """Brand mentions scan → digest. Cached 6hr, never raises."""
    business = (business_name or "").strip()[:120]
    if not business:
        return {"ok": False, "error": "business_name required", "mentions": []}
    query = business + (f" {city}" if (city or "").strip() else "")
    key = query.lower()

    cached = _cache_get(key)
    if cached:
        return {**cached, "cached": True}

    try:
        import asyncio

        news, reddit = await asyncio.gather(_fetch_google_news(query), _fetch_reddit(query))
    except Exception:
        news, reddit = [], []

    mentions: list[dict[str, Any]] = []
    for m in (news or []) + (reddit or []):
        m = dict(m)
        m["sentiment"] = _label(f"{m.get('title', '')} {m.get('snippet', '')}")
        mentions.append(m)

    breakdown: dict[str, int] = {}
    for m in mentions:
        breakdown[m["sentiment"]] = breakdown.get(m["sentiment"], 0) + 1

    reply_drafts = [
        {"title": m.get("title", ""), "url": m.get("url", ""), "draft": _reply_draft(business, m)}
        for m in mentions
        if m.get("sentiment") == "negative"
    ]

    digest = {
        "ok": True,
        "business_name": business,
        "query": query,
        "niche": (niche or "").strip(),
        "mentions": mentions,
        "breakdown": breakdown,
        "summary": _summary(business, mentions, breakdown),
        "reply_drafts": reply_drafts,
        "cached": False,
    }
    _append(_CACHE_FILE, {"key": key, "ts": _now(), "digest": digest})
    return digest


# --------------------------------------------------------------------------- #
# Weekly sweep — GATED BRAND_PULSE=1 (default OFF). Drafts only, NO send.
# --------------------------------------------------------------------------- #
def _flag_on() -> bool:
    return (os.getenv("BRAND_PULSE") or "").strip().lower() in ("1", "true", "yes", "on")


async def run_weekly_if_enabled(max_clients: int = 10) -> dict[str, Any]:
    """Active clients ka brand scan (gated). Run record + team event. Never raises."""
    if not _flag_on():
        return {"ok": False, "reason": "flag_off", "hint": "BRAND_PULSE=1 to enable"}
    out: dict[str, Any] = {"ok": True, "scanned": 0, "negatives": 0}
    try:
        from app.marketing import clients_store

        clients = clients_store.list_clients(status="active") or clients_store.list_clients()
        for c in (clients or [])[: max(1, max_clients)]:
            try:
                d = await scan(
                    str(c.get("business_name") or ""),
                    city=str(c.get("city") or "") or None,
                    niche=str(c.get("niche") or "") or None,
                )
                if not d.get("ok"):
                    continue
                out["scanned"] += 1
                out["negatives"] += len(d.get("reply_drafts") or [])
                _append(
                    _RUNS_FILE,
                    {
                        "ts": _now(),
                        "client_id": c.get("id"),
                        "business_name": d.get("business_name"),
                        "mentions": len(d.get("mentions") or []),
                        "breakdown": d.get("breakdown"),
                        "summary": d.get("summary"),
                        "reply_drafts": d.get("reply_drafts"),
                    },
                )
            except Exception as e:
                logger.debug(f"[brand_pulse] client scan skip: {e}")
        try:
            from app.platform.team import log_event

            log_event(
                "isha",
                "brand_pulse",
                f"{out['scanned']} clients scanned, {out['negatives']} negative drafts",
            )
        except Exception:
            pass
    except Exception as e:
        logger.info(f"[brand_pulse] weekly run err: {e}")
        out["ok"] = False
        out["error"] = str(e)[:160]
    return out


def runs(limit: int = 30) -> list[dict[str, Any]]:
    """Recent weekly-run records (newest first)."""
    items = _read(_RUNS_FILE)
    items.reverse()
    return items[: max(1, min(int(limit or 30), 200))]


__all__ = ["scan", "run_weekly_if_enabled", "runs", "parse_news_rss", "parse_reddit_json"]
