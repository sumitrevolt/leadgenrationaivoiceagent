"""
Google Search Console (GSC) rank tracking — FREE SEO observability layer.

Kyu: programmatic SEO pages (blog, /b/{slug} mini-sites) bante hain par koi
rank/impression tracking nahi tha (SEO skill audit 2026-08-11: ~0 inbound
visibility). Yeh module daily Search Console search-analytics data fetch karke
local JSONL snapshot banata hai — data humara rehta hai, koi paid API nahi.

INERT by design:
  - GSC_ENABLED=1 + credentials ke bina run_daily() no-op hai (safe).
  - Credentials = service-account JSON. Source priority:
      GSC_SERVICE_ACCOUNT_JSON env (path) → google_sheets_credentials settings
      (wahi service-account file, calendar_booking.py jaisa reuse) → off.
  - GSC_SITE_URL (default "sc-domain:leadsgenai.in" — domain property,
    saare subdomains cover karta hai; Search Console me property add karna
    hoga + DNS TXT verify — runbook memory/playbooks.md me).
  - Google libs installed nahi hain to graceful no-op (ImportError caught).

Output files (data/ = gitignored runtime state):
  - data/gsc_daily.jsonl  — har run ka pura snapshot (append-only history)
  - data/gsc_state.json   — latest summary (atomic replace) — admin route ise
    padhta hai.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
DEFAULT_SITE_URL = "sc-domain:leadsgenai.in"
DAILY_JSONL = os.path.join("data", "gsc_daily.jsonl")
STATE_JSON = os.path.join("data", "gsc_state.json")


def _setting(name: str) -> str:
    """Call-time env → settings fallback (calendar_booking.py pattern)."""
    v = os.getenv(name)
    if v is not None and str(v).strip() != "":
        return str(v).strip()
    return str(getattr(settings, name, "") or "").strip()


def enabled() -> bool:
    """GSC_ENABLED=1 + credentials present. Har call pe re-check (INERT default)."""
    flag = os.getenv("GSC_ENABLED", "0").strip().lower()
    if flag not in ("1", "true", "yes"):
        return False
    creds = _setting("GSC_SERVICE_ACCOUNT_JSON") or _setting("google_sheets_credentials")
    return bool(creds and os.path.exists(creds))


def site_url() -> str:
    return _setting("GSC_SITE_URL") or DEFAULT_SITE_URL


def _build_service():
    """Search Console API v3 service. Local imports → libs missing = None."""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning(
            "[gsc] google-api-python-client not installed — GSC inactive. "
            "Run: pip install google-api-python-client"
        )
        return None
    try:
        creds_path = _setting("GSC_SERVICE_ACCOUNT_JSON") or _setting("google_sheets_credentials")
        credentials = Credentials.from_service_account_file(creds_path, scopes=GSC_SCOPES)
        service = build("webmasters", "v3", credentials=credentials, cache_discovery=False)
        logger.info("[gsc] Search Console service constructed")
        return service
    except Exception as e:  # bad creds file / wrong scope — never crash the worker
        logger.error(f"[gsc] service build error: {e}")
        return None


def _fetch(service, site: str, days: int) -> dict[str, Any]:
    """Search Console searchanalytics query — 3 calls (date series, top queries,
    top pages). Sync API; caller ko to_thread me chalaana chahiye."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(1, int(days) - 1))
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["date"],
        "rowLimit": 366,
    }
    try:
        res = service.searchanalytics().query(siteUrl=site, body=body).execute(num_retries=2)
    except Exception as e:
        logger.error(f"[gsc] daily-series fetch failed: {e}")
        res = {}
    series = res.get("rows", [])
    top_queries = _query_rows(service, site, start, end, "query", 50)
    top_pages = _query_rows(service, site, start, end, "page", 50)
    agg = {
        "clicks": int(sum(r.get("clicks", 0) for r in series)),
        "impressions": int(sum(r.get("impressions", 0) for r in series)),
        "ctr": (
            (sum(r.get("clicks", 0) for r in series) / sum(r.get("impressions", 0) for r in series))
            if sum(r.get("impressions", 0) for r in series)
            else 0.0
        ),
        "position": (
            (
                sum(r.get("position", 0) * r.get("impressions", 0) for r in series)
                / sum(r.get("impressions", 0) for r in series)
            )
            if sum(r.get("impressions", 0) for r in series)
            else 0.0
        ),
    }
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "series": series,
        "top_queries": top_queries,
        "top_pages": top_pages,
        "aggregate": agg,
    }


def _query_rows(service, site: str, start, end, dimension: str, limit: int) -> list[dict[str, Any]]:
    try:
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": [dimension],
            "rowLimit": limit,
        }
        res = service.searchanalytics().query(siteUrl=site, body=body).execute(num_retries=2)
        return res.get("rows", [])
    except Exception as e:
        logger.debug(f"[gsc] {dimension} fetch failed: {e}")
        return []


def _write_state(snapshot: dict[str, Any]) -> None:
    """Latest summary → data/gsc_state.json (atomic tmp+replace, fail-safe)."""
    try:
        os.makedirs(os.path.dirname(STATE_JSON) or ".", exist_ok=True)
        state = {
            "site": site_url(),
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "aggregate": snapshot.get("aggregate", {}),
            "top_queries": snapshot.get("top_queries", [])[:10],
            "top_pages": snapshot.get("top_pages", [])[:10],
        }
        tmp = STATE_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_JSON)
    except Exception as e:
        logger.warning(f"[gsc] state write failed: {e}")


def _append_daily(snapshot: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(DAILY_JSONL) or ".", exist_ok=True)
        with open(DAILY_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot) + "\n")
    except Exception as e:
        logger.warning(f"[gsc] daily jsonl append failed: {e}")


def run_daily(days: int = 30) -> dict[str, Any]:
    """Daily GSC fetch. INERT: flag/creds/libs ke bina no-op result deta hai.
    Never raises — worker crash nahi hoga is module ki wajah se."""
    if not enabled():
        return {"enabled": False}
    service = _build_service()
    if service is None:
        return {"enabled": True, "ok": False, "reason": "service_unavailable"}
    try:
        snapshot = _fetch(service, site_url(), days)
        snapshot["fetched_at_utc"] = datetime.now(timezone.utc).isoformat()
        snapshot["site"] = site_url()
        _append_daily(snapshot)
        _write_state(snapshot)
        return {"enabled": True, "ok": True, "aggregate": snapshot.get("aggregate", {})}
    except Exception as e:
        logger.error(f"[gsc] run_daily failed: {e}")
        return {"enabled": True, "ok": False, "reason": str(e)[:200]}


async def run_daily_async(days: int = 30) -> dict[str, Any]:
    """Async entry (Celery/beat) — sync API call ko thread pe shift karta hai
    taaki worker event-loop block na ho (ML assets pattern)."""
    return await asyncio.to_thread(run_daily, days)


def latest_state() -> dict[str, Any]:
    """Admin overview ke liye latest summary (no-op if never fetched)."""
    try:
        with open(STATE_JSON, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"site": site_url(), "fetched_at_utc": None, "aggregate": {}}
    except Exception as e:
        logger.debug(f"[gsc] state read failed: {e}")
        return {"site": site_url(), "fetched_at_utc": None, "aggregate": {}}


def trend(days: int = 30) -> list[dict[str, Any]]:
    """gsc_daily.jsonl se last N daily snapshots (reverse-chron), admin chart ke liye."""
    try:
        with open(DAILY_JSONL, encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        out = []
        for ln in lines[-max(1, int(days)) :]:
            try:
                row = json.loads(ln)
                out.append(
                    {
                        "fetched_at_utc": row.get("fetched_at_utc"),
                        "end_date": row.get("end_date"),
                        "clicks": row.get("aggregate", {}).get("clicks", 0),
                        "impressions": row.get("aggregate", {}).get("impressions", 0),
                        "position": round(row.get("aggregate", {}).get("position", 0), 2),
                    }
                )
            except Exception:
                continue
        return out
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.debug(f"[gsc] trend read failed: {e}")
        return []
