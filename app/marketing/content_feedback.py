"""Content performance feedback loop — drafts ke baad system andha na rahe.

Kya karta:
- tracked_link(): har draft ke CTA link me utm_source auto + is.gd short link (free, no-key).
- record_feedback(): human/client 1-click "post chala / nahi chala" → jsonl + (chala to)
  channel_experiments.record_outcome attribution.
- theme_stats()/best_themes(): theme×format×niche level Laplace score — post_generator
  / content jobs ko pata chale kaunsa content convert karta hai.

Free-stack, defensive, NEVER raises. Store: data/content_feedback.jsonl
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "content_feedback.jsonl")
_SHORT_CACHE: dict[str, str] = {}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def shorten(url: str) -> str:
    """is.gd free shortener — fail ho to original URL hi lauta do (never raise)."""
    url = (url or "").strip()
    if not url.startswith("http"):
        return url
    if url in _SHORT_CACHE:
        return _SHORT_CACHE[url]
    try:
        import httpx

        r = httpx.get(
            f"https://is.gd/create.php?format=simple&url={quote(url, safe='')}",
            timeout=5,
        )
        if r.status_code == 200 and r.text.strip().startswith("http"):
            _SHORT_CACHE[url] = r.text.strip()
            return _SHORT_CACHE[url]
    except Exception as e:
        logger.debug(f"shorten failed: {e}")
    return url


def tracked_link(url: str, source: str, campaign: str = "") -> str:
    """URL me utm_source (+campaign) daal ke short karo — attribution-ready CTA."""
    url = (url or "").strip()
    if not url.startswith("http"):
        return url
    sep = "&" if "?" in url else "?"
    out = f"{url}{sep}utm_source={quote(source or 'content')}"
    if campaign:
        out += f"&utm_campaign={quote(campaign)}"
    return shorten(out)


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"content_feedback append failed: {e}")


def _read() -> list[dict[str, Any]]:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"content_feedback read failed: {e}")
        return []


def record_feedback(
    theme: str,
    worked: bool,
    fmt: str = "post",
    niche: str = "",
    post_id: str = "",
    channel: str = "",
    note: str = "",
) -> dict[str, Any]:
    """1-click feedback — worked=True pe channel bandit ko bhi outcome credit."""
    rec = {
        "ts": _now(),
        "theme": (theme or "").strip().lower()[:80],
        "format": (fmt or "post").strip().lower()[:40],
        "niche": (niche or "").strip().lower()[:60],
        "post_id": (post_id or "")[:80],
        "channel": (channel or "")[:40],
        "worked": bool(worked),
        "note": (note or "")[:200],
    }
    _append(rec)
    if worked and channel:
        try:
            from app.marketing import channel_experiments

            channel_experiments.record_outcome(channel, kind="content_feedback", note=rec["theme"])
        except Exception as e:
            logger.debug(f"bandit credit skip: {e}")
    return {"ok": True, "recorded": rec}


def theme_stats(niche: str = "") -> dict[str, Any]:
    """Theme×format ka Laplace-smoothed score (sparse feedback safe)."""
    rows = _read()
    if niche:
        rows = [r for r in rows if r.get("niche") == niche.strip().lower()]
    agg: dict[str, dict[str, int]] = {}
    for r in rows:
        key = f"{r.get('theme', '?')}|{r.get('format', 'post')}"
        d = agg.setdefault(key, {"worked": 0, "total": 0})
        d["total"] += 1
        d["worked"] += 1 if r.get("worked") else 0
    out = []
    for key, d in agg.items():
        theme, fmt = key.split("|", 1)
        score = (d["worked"] + 1) / (d["total"] + 2)  # Laplace
        out.append({"theme": theme, "format": fmt, **d, "score": round(score, 3)})
    out.sort(key=lambda x: (-x["score"], -x["total"]))
    return {"niche": niche, "themes": out, "total_feedback": len(rows)}


def best_themes(niche: str = "", n: int = 5) -> list[str]:
    """Content jobs ke liye top-N proven themes (empty = data nahi)."""
    return [t["theme"] for t in theme_stats(niche)["themes"][: max(1, n)]]
