"""Local Rank Tracker (BrightLocal-style) — ONGOING Google-local rank tracking.

Kyun: GBP-audit / website_auditor one-shot reports hain; clients ko RETENTION
hook chahiye — "aapka business 'solar installer pune' pe Google me #4 hai,
pichhle hafte #7 tha". Yeh module configured keywords ko regularly check karke
position history banata hai.

Design (project patterns):
- Places API (New) `places:searchText` — legacy textsearch hamari key pe
  DENIED hai (google_maps.py jaisa hi call style, X-Goog-FieldMask).
- NEVER raises — har failure pe error-dict / empty list.
- Lazy imports (httpx/settings handler ke andar).
- Quota care: per-run lookup cap (default 20, env `RANK_MAX_LOOKUPS`) —
  PROSPECT_MAX_LOOKUPS jaisa pattern.
- Scheduler gating: `run_if_enabled()` sirf `RANK_TRACKER=1` pe chalta
  (default OFF = zero behaviour change).

Stores (append-only jsonl, inquiries.jsonl pattern):
- data/rank_tracking.jsonl  — per-client config (client_id + keywords + city)
- data/rank_history.jsonl   — har check ka result (position over time)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CONFIG_FILE = os.path.join("data", "rank_tracking.jsonl")
_HISTORY_FILE = os.path.join("data", "rank_history.jsonl")

_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = (
    "places.displayName,places.nationalPhoneNumber,"
    "places.internationalPhoneNumber,places.id,places.formattedAddress"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _max_lookups() -> int:
    try:
        return max(1, min(100, int(os.getenv("RANK_MAX_LOOKUPS", "20") or 20)))
    except Exception:
        return 20


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
        logger.debug(f"[rank] read {path} failed: {e}")
    return out


def _append_jsonl(path: str, rec: dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[rank] append {path} failed: {e}")
        return False


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, path)
        return True
    except Exception as e:
        logger.warning(f"[rank] write {path} failed: {e}")
        return False


# --------------------------------------------------------------------------- #
# Matching (pure functions — unit-testable, no network)
# --------------------------------------------------------------------------- #
def _phone_digits(raw: str | None) -> str:
    """Last-10 digits (Indian mobile/landline compare ke liye)."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _norm_name(name: str | None) -> str:
    return " ".join(str(name or "").lower().replace("&", "and").split())


def _name_match(a: str, b: str) -> bool:
    """Fuzzy business-name match — substring ya token overlap >= 60%."""
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.6


def match_position(
    results: list[dict[str, Any]], business_name: str, phone: str | None = None
) -> int | None:
    """1-based position of the business in `results` (name fuzzy / phone exact).

    results = [{"name":..., "phone":...}, ...]. None = top-N me nahi mila.
    Pure function — tests isi pe chalte hain.
    """
    try:
        want_phone = _phone_digits(phone)
        for idx, r in enumerate(results, start=1):
            if want_phone and _phone_digits(r.get("phone")) == want_phone:
                return idx
            if _name_match(business_name, r.get("name") or ""):
                return idx
        return None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Places API (New) search — google_maps.py ka exact call style (REUSE pattern)
# --------------------------------------------------------------------------- #
async def _places_search(keyword: str, city: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Top-N local results for "keyword city". [] on any failure (never raises)."""
    try:
        from app.config import settings

        api_key = getattr(settings, "google_maps_api_key", None) or os.getenv(
            "GOOGLE_MAPS_API_KEY", ""
        )
        if not api_key:
            logger.debug("[rank] GOOGLE_MAPS key missing — search skipped")
            return []

        import httpx

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        body = {
            "textQuery": f"{keyword} in {city}",
            "maxResultCount": max(1, min(20, int(max_results))),
            "regionCode": "IN",
        }
        out: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_PLACES_URL, headers=headers, json=body, timeout=30.0)
            if resp.status_code != 200:
                logger.warning(f"[rank] Places(New) HTTP {resp.status_code}: {resp.text[:160]}")
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
                            "place_id": p.get("id", ""),
                            "address": p.get("formattedAddress", ""),
                        }
                    )
                except Exception:
                    continue
        return out
    except Exception as e:
        logger.warning(f"[rank] places search failed: {e}")
        return []


async def check_rank(
    business_name: str, phone: str | None, keyword: str, city: str
) -> dict[str, Any]:
    """Ek keyword pe client ki local-rank check (1-20 ya null). Never raises.

    Returns {keyword, city, position, top3, total_results, checked_at} —
    ya {"error": ...} jab key/input missing ho.
    """
    keyword = (keyword or "").strip()
    city = (city or "").strip()
    business_name = (business_name or "").strip()
    if not keyword or not city or not business_name:
        return {"error": "business_name, keyword aur city teeno chahiye"}
    try:
        results = await _places_search(keyword, city, max_results=20)
        if not results:
            return {
                "keyword": keyword,
                "city": city,
                "position": None,
                "top3": [],
                "total_results": 0,
                "checked_at": _now(),
                "error": "Places API se results nahi mile (key/quota check karo)",
            }
        position = match_position(results, business_name, phone)
        return {
            "keyword": keyword,
            "city": city,
            "position": position,
            "top3": [r.get("name") for r in results[:3]],
            "total_results": len(results),
            "checked_at": _now(),
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[rank] check_rank failed: {e}")
        return {"error": f"rank check fail: {e}"}


# --------------------------------------------------------------------------- #
# Config store (upsert per client) + history
# --------------------------------------------------------------------------- #
def track(
    client_id: str,
    keywords: list[str],
    city: str,
    business_name: str = "",
    phone: str = "",
) -> dict[str, Any]:
    """Client ke liye rank-tracking config upsert. Never raises."""
    try:
        client_id = (client_id or "").strip()
        if not client_id:
            return {"error": "client_id chahiye"}
        kws = [str(k).strip() for k in (keywords or []) if str(k).strip()][:10]
        if not kws:
            return {"error": "kam se kam 1 keyword do"}
        rows = _read_jsonl(_CONFIG_FILE)
        rows = [r for r in rows if r.get("client_id") != client_id]
        rec = {
            "client_id": client_id,
            "business_name": (business_name or "").strip()[:200],
            "phone": (phone or "").strip()[:20],
            "keywords": kws,
            "city": (city or "").strip()[:100],
            "updated_at": _now(),
        }
        rows.append(rec)
        _write_jsonl(_CONFIG_FILE, rows)
        return {"ok": True, "config": rec}
    except Exception as e:
        logger.warning(f"[rank] track failed: {e}")
        return {"error": str(e)}


def list_configs() -> list[dict[str, Any]]:
    return _read_jsonl(_CONFIG_FILE)


def history(client_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Rank history newest-first (optional client filter). Never raises."""
    try:
        rows = _read_jsonl(_HISTORY_FILE)
        if client_id:
            rows = [r for r in rows if r.get("client_id") == client_id]
        rows.sort(key=lambda r: str(r.get("checked_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit), 1000))]
    except Exception as e:
        logger.debug(f"[rank] history failed: {e}")
        return []


async def run_tracking(max_lookups: int | None = None) -> dict[str, Any]:
    """Saare configured client×keyword check karo (lookup cap ke saath).

    Har check = 1 Places lookup — quota care, default cap 20/run
    (env RANK_MAX_LOOKUPS). Results data/rank_history.jsonl me. Never raises.
    """
    cap = max_lookups if isinstance(max_lookups, int) and max_lookups > 0 else _max_lookups()
    summary: dict[str, Any] = {"ok": True, "checked": 0, "found": 0, "skipped": 0, "results": []}
    try:
        configs = list_configs()
        if not configs:
            summary["note"] = "koi rank config nahi — POST /api/seoops/rank/config se add karo"
            return summary
        used = 0
        for cfg in configs:
            name = cfg.get("business_name") or ""
            ph = cfg.get("phone") or ""
            city = cfg.get("city") or ""
            for kw in cfg.get("keywords") or []:
                if used >= cap:
                    summary["skipped"] += 1
                    continue
                used += 1
                res = await check_rank(name, ph, kw, city)
                if res.get("error") and res.get("total_results") is None:
                    summary["skipped"] += 1
                    continue
                rec = {"client_id": cfg.get("client_id"), "business_name": name, **res}
                _append_jsonl(_HISTORY_FILE, rec)
                summary["checked"] += 1
                if res.get("position"):
                    summary["found"] += 1
                summary["results"].append(rec)
        return summary
    except Exception as e:
        logger.warning(f"[rank] run_tracking failed: {e}")
        return {"ok": False, "error": str(e), **{k: summary.get(k) for k in ("checked", "found")}}


async def run_if_enabled() -> dict[str, Any]:
    """Scheduler hook — sirf RANK_TRACKER=1 pe chalta (default OFF). Never raises."""
    if not _flag("RANK_TRACKER"):
        return {"ok": False, "skipped": "RANK_TRACKER flag off"}
    try:
        return await run_tracking()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[rank] run_if_enabled failed: {e}")
        return {"ok": False, "error": str(e)}


__all__ = [
    "check_rank",
    "match_position",
    "track",
    "list_configs",
    "history",
    "run_tracking",
    "run_if_enabled",
]
