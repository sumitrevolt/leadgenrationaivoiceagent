"""Prospect Search + Saved Lists (Apollo.io ka core UX, free-stack).

Apollo ki asli taakat = filterable database + saved lists + list-pe-action.
Yahi humare apne prospects (scraped + imported) pe: filter search (niche/city/
status/has_email/text/min_score — score live compute, EXISTING lead_scoring),
saved lists (snapshot), list → cadence enroll (EXISTING cadence engine).

Plus: Apollo-CSV import — unke free exports (ya kisi bhi CSV) ko humari pipeline
me daalo (dedupe phone/email, prospector store + DB mirror, auto-score).

Store: data/lead_lists.jsonl. Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LISTS = os.path.join("data", "lead_lists.jsonl")


def _read_lists() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_LISTS):
            with open(_LISTS, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _write_lists(rows: list[dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(_LISTS) or ".", exist_ok=True)
        with open(_LISTS, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning(f"[lists] write failed: {e}")


_V2_ENABLED = None  # lazily cached (env PROSPECT_SCORE_V2=1; default OFF)


def _score_v2_on() -> bool:
    """Feature-flag gate: PROSPECT_SCORE_V2=1 → V2 scorer. Default OFF (V1 read
    path preserved — backward-compatible)."""
    global _V2_ENABLED
    if _V2_ENABLED is None:
        _V2_ENABLED = (os.environ.get("PROSPECT_SCORE_V2", "0") or "0").strip() == "1"
    return _V2_ENABLED


def _scorer_for():
    """V2 when flag on, else existing V1 (import-safe, never raises)."""
    if _score_v2_on():
        try:
            from app.platform.lead_scoring_v2 import score_lead_v2

            return score_lead_v2, "v2"
        except Exception:
            pass
    try:
        from app.platform.lead_scoring import score_lead

        return score_lead, "v1"
    except Exception:
        return None, "v1"


def search(
    niche: str = "",
    city: str = "",
    status: str = "",
    has_email: bool | None = None,
    q: str = "",
    min_score: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Apollo-style filter search over apne prospects. Score live compute
    (lead_scoring pure fn). Kabhi raise nahi."""
    try:
        from app.platform import prospector

        rows = prospector.list_prospects(limit=2000)
    except Exception:
        rows = []
    out: list[dict[str, Any]] = []
    qn = (q or "").strip().lower()
    scorer, _ver = _scorer_for()
    for r in rows:
        try:
            if niche and str(r.get("niche", "")).lower() != niche.lower():
                continue
            if city and city.lower() not in str(r.get("city", "")).lower():
                continue
            if status and str(r.get("status") or "ready").lower() != status.lower():
                continue
            em = str(r.get("email") or "")
            if has_email is True and "@" not in em:
                continue
            if has_email is False and "@" in em:
                continue
            if qn and qn not in json.dumps(r, ensure_ascii=False, default=str).lower():
                continue
            score = 0
            if scorer:
                try:
                    score = int(scorer(r))
                except Exception:
                    score = 0
            if score < int(min_score or 0):
                continue
            out.append({**r, "score": score})
        except Exception:
            continue
    out.sort(key=lambda x: x.get("score", 0), reverse=True)
    return out[: max(1, min(int(limit), 500))]


def create_list(
    name: str, prospect_ids: list[str] | None = None, filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Saved list — explicit ids YA filters-snapshot se. Kabhi raise nahi."""
    try:
        ids = list(prospect_ids or [])
        if not ids and filters:
            ids = [
                str(r.get("id"))
                for r in search(**{k: v for k, v in filters.items() if v is not None})
                if r.get("id")
            ]
        rec = {
            "id": uuid.uuid4().hex[:10],
            "name": (name or "list")[:80],
            "prospect_ids": ids,
            "filters": filters or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        rows = _read_lists()
        rows.append(rec)
        _write_lists(rows)
        return {"ok": True, "list": rec, "count": len(ids)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_lists() -> list[dict[str, Any]]:
    return [{**r, "count": len(r.get("prospect_ids") or [])} for r in _read_lists()][::-1]


def enroll_list_to_cadence(list_id: str) -> dict[str, Any]:
    """List ke saare prospects → cadence sequence (dedupe cadence khud karta).
    Sends apne channel-gates pe — ban-safe. Kabhi raise nahi."""
    try:
        target = next((r for r in _read_lists() if r.get("id") == list_id), None)
        if not target:
            return {"ok": False, "error": "list nahi mili"}
        from app.marketing import cadence
        from app.platform import prospector

        all_p = {str(r.get("id")): r for r in prospector.list_prospects(limit=2000)}
        enrolled = 0
        for pid in target.get("prospect_ids") or []:
            rec = all_p.get(str(pid))
            if rec:
                cadence.enroll(rec)
                enrolled += 1
        return {"ok": True, "enrolled": enrolled, "list": target.get("name")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --------------------- Apollo-CSV / rows import --------------------- #
_FIELD_ALIASES = {
    "business_name": ["business_name", "company", "company name", "organization", "account name"],
    "name": ["name", "full name", "first name", "contact"],
    "email": ["email", "work email", "email address"],
    "phone": [
        "phone",
        "mobile",
        "phone number",
        "work direct phone",
        "mobile phone",
        "corporate phone",
    ],
    "city": ["city", "location", "company city"],
    "niche": ["niche", "industry", "keywords"],
    "website": ["website", "company website", "website url", "domain"],
    "title": ["title", "job title", "designation"],
}


def _map_row(raw: dict[str, Any]) -> dict[str, Any]:
    low = {str(k).strip().lower(): v for k, v in (raw or {}).items()}
    out: dict[str, Any] = {}
    for field, aliases in _FIELD_ALIASES.items():
        for a in aliases:
            if a in low and str(low[a] or "").strip():
                out[field] = str(low[a]).strip()
                break
    return out


def import_rows(rows: list[dict[str, Any]], source: str = "apollo_import") -> dict[str, Any]:
    """Apollo export (ya koi bhi) rows → prospector store (dedupe phone/email)
    + DB mirror + auto-score-ready. Kabhi raise nahi."""
    added = skipped = 0
    try:
        from app.platform import prospector

        existing = prospector.list_prospects(limit=5000)
        seen_phones = {
            "".join(c for c in str(r.get("phone") or "") if c.isdigit())[-10:] for r in existing
        }
        seen_emails = {str(r.get("email") or "").lower() for r in existing if r.get("email")}
        for raw in rows or []:
            m = _map_row(raw)
            biz = m.get("business_name") or m.get("name") or ""
            if not biz:
                skipped += 1
                continue
            ph = "".join(c for c in str(m.get("phone") or "") if c.isdigit())[-10:]
            em = str(m.get("email") or "").lower()
            if (ph and ph in seen_phones) or (em and em in seen_emails):
                skipped += 1
                continue
            rec = {
                "id": uuid.uuid4().hex[:12],
                "business_name": biz[:120],
                "contact_name": (m.get("name") or "")[:80],
                "title": (m.get("title") or "")[:80],
                "phone": ph,
                "email": em,
                "website": (m.get("website") or "")[:200],
                "niche": (m.get("niche") or "general").lower()[:60],
                "city": (m.get("city") or "")[:80],
                "status": "ready",
                "source": source,
                "found_at": datetime.now(timezone.utc).isoformat(),
            }
            if prospector._append(rec):
                added += 1
                if ph:
                    seen_phones.add(ph)
                if em:
                    seen_emails.add(em)
        try:
            from app.platform import team

            team.log_event(
                "rohan", "prospects_imported", f"{added} imported ({source}), {skipped} dup/skip"
            )
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[lists] import failed: {e}")
        return {"ok": False, "error": str(e), "added": added, "skipped": skipped}
    return {"ok": True, "added": added, "skipped": skipped}


def import_csv_text(csv_text: str, source: str = "apollo_import") -> dict[str, Any]:
    """Raw CSV paste → rows → import_rows. Kabhi raise nahi."""
    try:
        import csv
        import io

        reader = csv.DictReader(io.StringIO(csv_text or ""))
        return import_rows(list(reader), source)
    except Exception as e:
        return {"ok": False, "error": str(e), "added": 0, "skipped": 0}
