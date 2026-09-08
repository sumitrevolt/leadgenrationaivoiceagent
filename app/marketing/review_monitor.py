"""Google review monitor (Birdeye/Podium-pattern, free via Places API New).

Har active client ke naye Google reviews roz check karta — naya review mila to
AI Hinglish reply DRAFT (EXISTING review_replies engine reuse) + negative pe
alert. Auto-post NAHI (GBP API approval pending) — human 1-click.

GATED `REVIEW_MONITOR=1` + GOOGLE_MAPS_API_KEY (bina key = silent skip).
Cost: 1 Places searchText per client per run (Places New free tier me theek).
Store: data/review_monitor_seen.jsonl + review_monitor_drafts.jsonl.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SEEN = os.path.join("data", "review_monitor_seen.jsonl")
_DRAFTS = os.path.join("data", "review_monitor_drafts.jsonl")


def _enabled() -> bool:
    return os.environ.get("REVIEW_MONITOR", "0").strip().lower() in ("1", "true", "yes")


def _api_key() -> str:
    k = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if k:
        return k
    try:
        from app.config import settings

        return str(getattr(settings, "google_maps_api_key", "") or "")
    except Exception:
        return ""


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


async def fetch_reviews(business_name: str, city: str = "") -> list[dict[str, Any]]:
    """Places API (New) searchText se top reviews (max ~5). [] on any failure."""
    key = _api_key()
    if not key or not business_name:
        return []
    try:
        import httpx

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.userRatingCount,places.reviews",
        }
        body = {
            "textQuery": f"{business_name} {city}".strip(),
            "maxResultCount": 1,
            "regionCode": "IN",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers,
                json=body,
                timeout=20.0,
            )
            if resp.status_code != 200:
                logger.debug(f"[review_monitor] HTTP {resp.status_code}: {resp.text[:120]}")
                return []
            places = resp.json().get("places") or []
            if not places:
                return []
            out = []
            for rv in places[0].get("reviews") or []:
                out.append(
                    {
                        "review_id": str(rv.get("name", ""))[-40:],
                        "rating": rv.get("rating"),
                        "text": str(((rv.get("text") or {}).get("text")) or "")[:500],
                        "author": str(
                            ((rv.get("authorAttribution") or {}).get("displayName")) or ""
                        )[:80],
                    }
                )
            return out
    except Exception as e:
        logger.debug(f"[review_monitor] fetch skip: {e}")
        return []


async def run_check(max_clients: int = 15) -> dict[str, Any]:
    """Daily sweep saare active clients pe. GATED (off/bina-key = no-op)."""
    if not _enabled():
        return {"enabled": False}
    if not _api_key():
        return {"enabled": True, "skipped": "no GOOGLE_MAPS_API_KEY"}
    new_drafts = 0
    try:
        from app.marketing.clients_store import list_clients

        seen_ids = {r.get("review_id") for r in _read(_SEEN)}
        for c in (list_clients("active") or [])[:max_clients]:
            biz = str(c.get("business_name") or "")
            try:
                reviews = await fetch_reviews(biz, str(c.get("city") or ""))
                for rv in reviews:
                    rid = rv.get("review_id")
                    if not rid or rid in seen_ids:
                        continue
                    seen_ids.add(rid)
                    _append(
                        _SEEN,
                        {
                            "review_id": rid,
                            "client_id": c.get("id"),
                            "at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    # AI reply draft (EXISTING engine reuse)
                    drafts = []
                    try:
                        from app.marketing import review_replies

                        res = await review_replies.generate_replies(
                            review_text=rv.get("text", ""),
                            rating=rv.get("rating"),
                            business_name=biz,
                        )
                        drafts = res.get("replies") or res.get("drafts") or []
                    except Exception:
                        pass
                    _append(
                        _DRAFTS,
                        {
                            "client_id": c.get("id"),
                            "business_name": biz,
                            **rv,
                            "reply_drafts": drafts[:3],
                            "at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    new_drafts += 1
            except Exception:
                continue
        if new_drafts:
            try:
                from app.platform import team

                team.log_event(
                    "isha", "review_monitor", f"{new_drafts} naye reviews — reply drafts ready"
                )
            except Exception:
                pass
        return {"enabled": True, "new_reviews": new_drafts}
    except Exception as e:
        logger.warning(f"[review_monitor] run_check failed: {e}")
        return {"enabled": True, "error": str(e)}


def recent_drafts(limit: int = 20) -> list[dict[str, Any]]:
    return _read(_DRAFTS)[-limit:][::-1]
