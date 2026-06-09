"""Niche-driven scraping orchestrator — saare 42 NICHES auto-cover karta.

PROBLEM: `prospector.py` default sirf 4 niches scrape karta (`_DEFAULT_TARGETS`);
`app.niches.NICHES` ke 42 niches ke rich `keywords` use nahi hote.

YEH module EXISTING prospector pipeline (scrape + dedupe + persist) ko drive karta
hai — har niche ke apne `keywords` se — **round-robin batch** me. Roz ek batch
chalta → kuch din me saare niches cover. Prospector ko TOUCH nahi karta:
`PROSPECT_TARGETS` env inject karke `run_prospecting()` call karta, fir env restore.

Cursor `data/niche_prospect_cursor.json` me — rotation persist hota. Tier filter
(S/A/B) optional. Free (Google Maps + OSM Overpass jo prospector already use karta).
Import-safe, kabhi raise nahi karta.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CURSOR = os.path.join("data", "niche_prospect_cursor.json")
_DEFAULT_CITIES = ["Pune", "Mumbai", "Nagpur", "Nashik", "Thane"]


def _all_niche_keys(tier: str | None = None, leadgen_only: bool = True) -> list[str]:
    """NICHES keys (optional tier filter). leadgen_only=True → marketing-only skip
    (un businesses ko hum scrape nahi karte jinko sirf marketing bechni hai? nahi —
    leadgen+both dono prospect-worthy; pure 'marketing' category bhi business hai).
    """
    try:
        from app.niches import NICHES
    except Exception:
        return []
    keys = []
    for k, cfg in NICHES.items():
        if not isinstance(cfg, dict):
            continue
        if tier and str(cfg.get("tier", "")).upper() != tier.upper():
            continue
        keys.append(k)
    return keys


def _read_cursor() -> int:
    try:
        if os.path.exists(_CURSOR):
            with open(_CURSOR, encoding="utf-8") as f:
                return int(json.load(f).get("i", 0))
    except Exception:
        pass
    return 0


def _write_cursor(i: int) -> None:
    try:
        os.makedirs(os.path.dirname(_CURSOR) or ".", exist_ok=True)
        with open(_CURSOR, "w", encoding="utf-8") as f:
            json.dump({"i": i}, f)
    except Exception as e:
        logger.debug(f"[niche_prospector] cursor write skip: {e}")


def build_targets(
    tier: str | None = None,
    batch: int = 8,
    max_keywords: int = 2,
    cities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Next `batch` niches (round-robin) ke targets — har niche ke first
    `max_keywords` keywords se. Returns prospector-shape list (niche/query/cities).
    """
    from app.niches import NICHES

    keys = _all_niche_keys(tier)
    if not keys:
        return []
    n = len(keys)
    start = _read_cursor() % n
    picked = [keys[(start + j) % n] for j in range(min(batch, n))]
    cities = cities or _DEFAULT_CITIES
    targets: list[dict[str, Any]] = []
    for nk in picked:
        cfg = NICHES.get(nk) or {}
        kws = [str(x) for x in (cfg.get("keywords") or []) if str(x).strip()][:max_keywords]
        if not kws:
            kws = [(cfg.get("name") or nk).replace("_", " ")]
        for kw in kws:
            targets.append({"niche": nk, "query": kw, "cities": cities})
    return targets


async def run(
    tier: str | None = None,
    batch: int = 8,
    limit_per_query: int = 6,
    cities: list[str] | None = None,
    advance: bool = True,
) -> dict[str, Any]:
    """Next niche-batch scrape karo (existing prospector se). Kabhi raise nahi.

    advance=True → cursor aage badhao (agla run agle niches karega).
    """
    targets = build_targets(tier=tier, batch=batch, cities=cities)
    if not targets:
        return {"ok": False, "reason": "no niches/targets", "covered": []}

    covered = sorted({t["niche"] for t in targets})
    old = os.environ.get("PROSPECT_TARGETS")
    os.environ["PROSPECT_TARGETS"] = json.dumps(targets, ensure_ascii=False)
    result: Any = None
    try:
        from app.platform import prospector

        result = await prospector.run_prospecting(limit_per_query)
    except Exception as e:
        logger.warning(f"[niche_prospector] run failed: {e}")
        result = {"error": str(e)[:200]}
    finally:
        if old is None:
            os.environ.pop("PROSPECT_TARGETS", None)
        else:
            os.environ["PROSPECT_TARGETS"] = old

    if advance:
        keys = _all_niche_keys(tier)
        if keys:
            # SKIP-SAFE: cursor ko ACTUALLY-scraped niches se aage badhao (lookup-cap
            # se aksar batch ka sirf pehla niche hi scrape hota — batch se advance
            # karne par baaki skip ho jaate). by_niche se real count lo, min 1.
            scraped = 0
            try:
                byn = (result or {}).get("by_niche") if isinstance(result, dict) else None
                scraped = len(byn) if isinstance(byn, dict) else 0
            except Exception:
                scraped = 0
            step = max(1, scraped or batch)
            _write_cursor((_read_cursor() + step) % len(keys))

    logger.info(f"[niche_prospector] scraped niches: {covered}")
    return {"ok": True, "covered": covered, "targets": len(targets), "result": result}


__all__ = ["build_targets", "run", "_all_niche_keys"]
