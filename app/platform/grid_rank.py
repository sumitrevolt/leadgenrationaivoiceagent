"""3×3 local grid rank tracker (Synup/LocalFalcon parity) — geo-grid GBP ranking.

Kyun: single-point rank (app/platform/rank_tracker.py) "city me #4" batata hai,
par local rank LOCATION pe depend karta hai — station ke paas #2, Kothrud me #9.
Yeh module 9 grid points (center ± offsets) pe Places(New) searchText
locationBias ke saath chala ke per-point rank deta hai + Hinglish summary.

Design (project patterns, rank_tracker REUSE):
- Places API (New) call style + fuzzy match = rank_tracker ka hi (match_position
  REUSE — duplicate matching logic NAHI).
- NEVER raises — error/quota pe {"ok": False, "reason"/"error": ...}.
- COST CAP: max 9 lookups/call (fixed 3×3) + max 3 keyword-runs/day
  (data/grid_rank_runs.jsonl counter) — Places quota safe.
- httpx ASYNC, 10s timeout per lookup, 9 points asyncio.gather (parallel) —
  endpoint `asyncio.wait_for(..., 25)` me poora call fit hota hai.
- Key missing → {"ok": False, "reason": "maps_key_missing"} (graceful).

Store: data/grid_rank_runs.jsonl (append-only — daily counter + history).
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RUNS_FILE = os.path.join("data", "grid_rank_runs.jsonl")
_DAILY_CAP = 3  # max keyword grid-runs per day (9 lookups each = 27 max/day)

_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = (
    "places.displayName,places.nationalPhoneNumber,"
    "places.internationalPhoneNumber,places.id,places.formattedAddress"
)

_ROW_LABEL = {-1: "North", 0: "", 1: "South"}
_COL_LABEL = {-1: "West", 0: "", 1: "East"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
        logger.debug(f"[grid] read {path} failed: {e}")
    return out


def _append_jsonl(path: str, rec: dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[grid] append {path} failed: {e}")
        return False


# --------------------------------------------------------------------------- #
# Pure geometry (unit-testable, no network)
# --------------------------------------------------------------------------- #
def grid_points(lat: float, lng: float, radius_km: float = 2.0) -> list[dict[str, Any]]:
    """9 points: center + 8 around (±radius_km). km→degree approx (India-fine)."""
    radius_km = max(0.5, min(10.0, float(radius_km)))
    lat_step = radius_km / 110.574
    lng_step = radius_km / (111.320 * max(0.2, math.cos(math.radians(float(lat)))))
    pts: list[dict[str, Any]] = []
    for row in (-1, 0, 1):
        for col in (-1, 0, 1):
            pts.append(
                {
                    "row": row,
                    "col": col,
                    "lat": round(float(lat) + row * lat_step, 6),
                    "lng": round(float(lng) + col * lng_step, 6),
                    "label": point_label(row, col),
                }
            )
    return pts


def point_label(row: int, col: int) -> str:
    if row == 0 and col == 0:
        return "Center"
    return (
        "-".join(x for x in (_ROW_LABEL.get(row, ""), _COL_LABEL.get(col, "")) if x)
    ) or "Center"


def runs_today() -> int:
    """Aaj kitne grid-runs ho chuke (daily cap counter). Never raises."""
    try:
        today = _today()
        return sum(
            1 for r in _read_jsonl(_RUNS_FILE) if str(r.get("checked_at", "")).startswith(today)
        )
    except Exception:
        return 0


def summarize(grid: list[dict[str, Any]]) -> str:
    """Hinglish summary — best/worst point + action. Pure function."""
    try:
        found = [g for g in grid if isinstance(g.get("rank"), int)]
        if not found:
            return (
                "Kisi bhi grid point pe top-20 me nahi mile — GBP optimize karo "
                "(category, photos, reviews) aur /audit se full report lo."
            )
        best = min(found, key=lambda g: g["rank"])
        worst = max(found, key=lambda g: g["rank"])
        missing = len(grid) - len(found)
        line = f"{best['label']} me rank {best['rank']}"
        if worst is not best and worst["rank"] != best["rank"]:
            line += f", {worst['label']} me {worst['rank']} — wahan GBP posts + reviews badhao"
        if missing:
            line += f". {missing} points pe top-20 ke bahar — un areas me visibility weak hai."
        return line
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Places(New) searchText with locationBias (rank_tracker call style + 10s timeout)
# --------------------------------------------------------------------------- #
def _api_key() -> str:
    try:
        from app.config import settings

        return getattr(settings, "google_maps_api_key", None) or os.getenv(
            "GOOGLE_MAPS_API_KEY", ""
        )
    except Exception:
        return os.getenv("GOOGLE_MAPS_API_KEY", "")


async def _places_search_at(
    keyword: str, lat: float, lng: float, radius_m: int, api_key: str
) -> list[dict[str, Any]]:
    """Top-20 results biased to a point. [] on any failure (never raises)."""
    try:
        import httpx

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        body = {
            "textQuery": keyword,
            "maxResultCount": 20,
            "regionCode": "IN",
            "locationBias": {
                "circle": {
                    "center": {"latitude": float(lat), "longitude": float(lng)},
                    "radius": max(500, min(50000, int(radius_m))),
                }
            },
        }
        out: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_PLACES_URL, headers=headers, json=body, timeout=10.0)
            if resp.status_code != 200:
                logger.warning(f"[grid] Places(New) HTTP {resp.status_code}: {resp.text[:160]}")
                return []
            for p in resp.json().get("places", []) or []:
                try:
                    name = (p.get("displayName") or {}).get("text", "").strip()
                    if not name:
                        continue
                    out.append(
                        {
                            "name": name,
                            "phone": p.get("nationalPhoneNumber")
                            or p.get("internationalPhoneNumber"),
                        }
                    )
                except Exception:
                    continue
        return out
    except Exception as e:
        logger.warning(f"[grid] point search failed: {e}")
        return []


async def grid_check(
    keyword: str,
    lat: float,
    lng: float,
    business_name: str,
    radius_km: float = 2.0,
    phone: str = "",
) -> dict[str, Any]:
    """3×3 grid rank check — 9 Places lookups (parallel), per-point rank ya ">20".

    Cost caps: 9 lookups/call (fixed), 3 runs/day. Never raises.
    """
    try:
        keyword = (keyword or "").strip()
        business_name = (business_name or "").strip()
        if not keyword or not business_name:
            return {"ok": False, "error": "keyword aur business_name dono chahiye"}
        try:
            lat = float(lat)
            lng = float(lng)
        except Exception:
            return {"ok": False, "error": "lat/lng valid numbers chahiye"}

        api_key = _api_key()
        if not api_key:
            return {"ok": False, "reason": "maps_key_missing"}

        if runs_today() >= _DAILY_CAP:
            return {
                "ok": False,
                "reason": "daily_cap_reached",
                "message": f"Aaj ke {_DAILY_CAP} grid-runs ho chuke (quota care) — kal try karo.",
            }

        # REUSE rank_tracker ka fuzzy matcher (duplicate logic nahi)
        from app.platform.rank_tracker import match_position

        pts = grid_points(lat, lng, radius_km)
        radius_m = int(max(0.5, min(10.0, float(radius_km))) * 1000)

        import asyncio

        batches = await asyncio.gather(
            *(_places_search_at(keyword, p["lat"], p["lng"], radius_m, api_key) for p in pts),
            return_exceptions=True,
        )

        grid: list[dict[str, Any]] = []
        ranks: list[int] = []
        for p, results in zip(pts, batches):
            if isinstance(results, BaseException) or not results:
                grid.append({**p, "rank": None, "note": "no_results"})
                continue
            pos = match_position(results, business_name, phone or None)
            if pos is None:
                grid.append({**p, "rank": None, "note": ">20"})
            else:
                grid.append({**p, "rank": pos})
                ranks.append(pos)

        avg_rank = round(sum(ranks) / len(ranks), 1) if ranks else None
        rec = {
            "ok": True,
            "keyword": keyword,
            "business_name": business_name,
            "center": {"lat": lat, "lng": lng},
            "radius_km": float(radius_km),
            "grid": grid,
            "found_points": len(ranks),
            "avg_rank": avg_rank,
            "summary": summarize(grid),
            "lookups_used": len(pts),
            "checked_at": _now(),
        }
        _append_jsonl(_RUNS_FILE, rec)
        return rec
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[grid] grid_check failed: {e}")
        return {"ok": False, "error": str(e)}


def recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    """Recent grid runs newest-first. Never raises."""
    try:
        rows = _read_jsonl(_RUNS_FILE)
        rows.sort(key=lambda r: str(r.get("checked_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit), 100))]
    except Exception as e:
        logger.debug(f"[grid] recent_runs failed: {e}")
        return []


__all__ = ["grid_check", "grid_points", "point_label", "summarize", "runs_today", "recent_runs"]
