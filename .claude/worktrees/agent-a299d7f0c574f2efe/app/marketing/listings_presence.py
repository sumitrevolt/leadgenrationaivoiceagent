"""India listings presence score — NAP/citation checklist (NO scraping).

Kyun: local SEO ka base = consistent listings (Google, Justdial, Sulekha...).
Competitors (Synup/BrightLocal) auto-scan bechte hain — par Justdial/Sulekha/
IndiaMART auto-scrape = ToS violation (project `_BLOCKED_DOMAINS` policy).
Isliye yeh module ZERO HTTP fetch karta hai: curated directory list + manual
deep-link search URLs (human khud click karke dekhe) + self-reported status
se 0-100 score + Hinglish gap tips.

Design: pure file-IO (no network, no LLM) — public-safe by construction.
NEVER raises. Store: data/listings_status.jsonl (per-client self-reported).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STATUS_FILE = os.path.join("data", "listings_status.jsonl")

# Curated India directories — key, naam, weight (sum=100), kyu (Hinglish),
# search-template ({q} = quoted "business city"), free listing URL.
# POLICY: in URLs ka HTTP fetch KABHI nahi — sirf manual deep-links.
_DIRECTORIES: list[dict[str, Any]] = [
    {
        "key": "google_business",
        "name": "Google Business Profile",
        "weight": 30,
        "why": "Local search + Maps ka #1 source — iske bina local customers milte hi nahi.",
        "search_url": "https://www.google.com/maps/search/{q}",
        "listing_url": "https://business.google.com/create",
    },
    {
        "key": "justdial",
        "name": "Justdial",
        "weight": 12,
        "why": "India ka sabse bada local directory — call-leads ke liye strong.",
        "search_url": "https://www.justdial.com/search?q={q}",
        "listing_url": "https://www.justdial.com/Free-Listing",
    },
    {
        "key": "sulekha",
        "name": "Sulekha",
        "weight": 8,
        "why": "Services (tuition, repair, events) categories me high-intent leads.",
        "search_url": "https://www.sulekha.com/search?keyword={q}",
        "listing_url": "https://www.sulekha.com/business-registration",
    },
    {
        "key": "indiamart",
        "name": "IndiaMART",
        "weight": 8,
        "why": "B2B/wholesale buyers ka sabse bada platform — manufacturer/trader ke liye must.",
        "search_url": "https://dir.indiamart.com/search.mp?ss={q}",
        "listing_url": "https://seller.indiamart.com/",
    },
    {
        "key": "tradeindia",
        "name": "TradeIndia",
        "weight": 5,
        "why": "Doosra bada B2B directory — extra backlink + buyer inquiries.",
        "search_url": "https://www.tradeindia.com/search.html?keyword={q}",
        "listing_url": "https://www.tradeindia.com/register/",
    },
    {
        "key": "facebook",
        "name": "Facebook Page",
        "weight": 10,
        "why": "Social proof + reviews + WhatsApp link — customers yahin check karte hain.",
        "search_url": "https://www.facebook.com/search/pages/?q={q}",
        "listing_url": "https://www.facebook.com/pages/create",
    },
    {
        "key": "instagram",
        "name": "Instagram Business",
        "weight": 8,
        "why": "Young customers ka discovery channel — photos/reels se trust banta hai.",
        "search_url": "https://www.instagram.com/explore/search/keyword/?q={q}",
        "listing_url": "https://business.instagram.com/getting-started",
    },
    {
        "key": "apple_maps",
        "name": "Apple Maps (Business Connect)",
        "weight": 6,
        "why": "iPhone users ka default Maps — free listing, competitors miss karte hain.",
        "search_url": "https://maps.apple.com/search?query={q}",
        "listing_url": "https://businessconnect.apple.com/",
    },
    {
        "key": "bing_places",
        "name": "Bing Places",
        "weight": 6,
        "why": "Bing/Copilot AI-search isi se uthata hai — GBP se import 5-min me ho jata hai.",
        "search_url": "https://www.bing.com/maps?q={q}",
        "listing_url": "https://www.bingplaces.com/",
    },
    {
        "key": "mapmyindia",
        "name": "MapmyIndia (Mappls)",
        "weight": 7,
        "why": "Indian cars/apps ka native map — local India traffic ke liye free listing.",
        "search_url": "https://www.mappls.com/search/{q}",
        "listing_url": "https://about.mappls.com/places/",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: str) -> list[dict[str, Any]]:
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
        logger.debug(f"[listings] read {path} failed: {e}")
    return out


def _append_jsonl(path: str, rec: dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[listings] append {path} failed: {e}")
        return False


# --------------------------------------------------------------------------- #
# Checklist + score (pure functions — no network)
# --------------------------------------------------------------------------- #
def checklist(business_name: str, city: str = "", niche: str = "") -> dict[str, Any]:
    """Curated directories + manual deep-link search URLs (LINK only, NO fetch)."""
    try:
        business_name = (business_name or "").strip()
        if not business_name:
            return {"ok": False, "error": "business_name chahiye"}
        q = quote_plus(f'"{business_name}" {city}'.strip())
        dirs = []
        for d in _DIRECTORIES:
            dirs.append(
                {
                    "key": d["key"],
                    "name": d["name"],
                    "weight": d["weight"],
                    "why": d["why"],
                    "search_url": d["search_url"].format(q=q),
                    "listing_url": d["listing_url"],
                }
            )
        return {
            "ok": True,
            "business_name": business_name,
            "city": city,
            "niche": niche,
            "directories": dirs,
            "how": (
                "Har 'search_url' khol ke dekho business listed hai ya nahi, phir "
                "POST /api/localseo/listings-status se present/absent mark karo — "
                "score + gap tips mil jayenge. (Auto-scan ToS-safe nahi — manual hi sahi.)"
            ),
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[listings] checklist failed: {e}")
        return {"ok": False, "error": str(e)}


def score(present: dict[str, Any] | None) -> dict[str, Any]:
    """Self-reported present-map → weighted 0-100 + Hinglish gap tips. Never raises."""
    try:
        present = present if isinstance(present, dict) else {}
        total = 0
        gaps: list[dict[str, Any]] = []
        present_keys: list[str] = []
        for d in _DIRECTORIES:
            if bool(present.get(d["key"])):
                total += d["weight"]
                present_keys.append(d["key"])
            else:
                gaps.append(d)
        gaps.sort(key=lambda d: -d["weight"])
        tips = [
            f"{d['name']} pe FREE listing banao ({d['listing_url']}) — {d['why']}" for d in gaps[:5]
        ]
        if total >= 80:
            verdict = "Listings presence solid hai — ab reviews + posts pe focus karo."
        elif total >= 50:
            verdict = (
                "Theek hai, par gaps hain — missing directories pe listing banao (sab FREE hain)."
            )
        else:
            verdict = (
                "Listings presence weak hai — customers aur AI search dono ko aap mil nahi rahe."
            )
        return {
            "ok": True,
            "score": min(100, total),
            "present": present_keys,
            "missing": [d["key"] for d in gaps],
            "verdict": verdict,
            "tips": tips,
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[listings] score failed: {e}")
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# Self-reported status store (per client)
# --------------------------------------------------------------------------- #
def save_status(client_id: str, present: dict[str, Any]) -> dict[str, Any]:
    """Client ka self-reported listings status save (append) + scored. Never raises."""
    try:
        client_id = (client_id or "").strip()
        if not client_id:
            return {"ok": False, "error": "client_id chahiye"}
        valid_keys = {d["key"] for d in _DIRECTORIES}
        clean = {k: bool(v) for k, v in (present or {}).items() if k in valid_keys}
        scored = score(clean)
        rec = {
            "client_id": client_id,
            "present": clean,
            "score": scored.get("score", 0),
            "updated_at": _now(),
        }
        _append_jsonl(_STATUS_FILE, rec)
        return {
            "ok": True,
            "saved": rec,
            **{k: scored.get(k) for k in ("verdict", "tips", "missing")},
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[listings] save_status failed: {e}")
        return {"ok": False, "error": str(e)}


def get_status(client_id: str) -> dict[str, Any]:
    """Client ka latest self-reported status + live score. Never raises."""
    try:
        client_id = (client_id or "").strip()
        rows = [r for r in _read_jsonl(_STATUS_FILE) if r.get("client_id") == client_id]
        if not rows:
            return {
                "ok": True,
                "client_id": client_id,
                "status": None,
                "note": "Abhi koi status saved nahi — pehle checklist se manual check karo.",
            }
        # Newest-wins, deterministically. The jsonl is append-only so file order IS
        # chronological; sort ASCENDING by updated_at (stable) and take the LAST row.
        # Don't sort desc + take rows[0]: on coarse-resolution clocks (Windows ~15ms
        # tick) two rapid saves can share a timestamp, and the tie then returns the
        # OLDER record. Ascending + rows[-1] keeps append order as the tiebreak so the
        # most-recently-saved status always wins.
        rows.sort(key=lambda r: str(r.get("updated_at") or ""))
        latest = rows[-1]
        return {
            "ok": True,
            "client_id": client_id,
            "status": latest,
            **score(latest.get("present")),
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[listings] get_status failed: {e}")
        return {"ok": False, "error": str(e)}


def directories() -> list[dict[str, Any]]:
    """Raw curated list (read-only copy)."""
    return [dict(d) for d in _DIRECTORIES]


__all__ = ["checklist", "score", "save_status", "get_status", "directories"]
