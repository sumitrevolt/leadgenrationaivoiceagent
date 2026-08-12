"""Dynamic segments (Mautic parity) — condition-based LIVE auto-grouping.

Static saved lists (app/platform/prospect_lists.py) = frozen snapshots.
Yeh module = DYNAMIC segments: ek segment = conditions ka set jo HAR baar
live prospect/lead pool ke against evaluate hota hai (recompute on demand,
NOT a frozen snapshot).

Pool loader REUSE karta hai — app/platform/prospect_lists.search() (jo already
niche/city/status/has_email/min_score filter + live score compute karta).
Koi naya pool data-file invent NAHI.

Segment record:
  {id, name, match: "all"|"any", conditions: [{field, op, value}],
   created_at, updated_at}

Store: data/segments.jsonl (atomic locked rewrite — sales_pipeline pattern).
Import-safe, lazy app.* imports, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "segments.jsonl")

# Supported ops (Mautic-style). Numeric ops apply to numeric fields (lead_score).
SUPPORTED_OPS = ["eq", "ne", "contains", "gt", "gte", "lt", "lte", "in", "exists"]

# Supported fields -> REAL prospect/lead attribute names + type hint.
# Source: app/platform/prospect_lists.search() output rows = prospector record
# (id, business_name, contact_name, phone, email, website, niche, city, status,
#  source) + computed `score`. has_email = derived (email me "@").
SUPPORTED_FIELDS: dict[str, str] = {
    "niche": "string",
    "city": "string",
    "status": "string",
    "source": "string",
    "business_name": "string",
    "lead_score": "number",  # mapped to record `score`
    "has_email": "bool",  # derived from email
    "email": "string",
}


# --------------------------- store helpers --------------------------- #
def _read_all() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _write_all(rows: list[dict[str, Any]]) -> None:
    try:
        from app.utils.file_lock import locked_rewrite

        content = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
        if not locked_rewrite(_STORE, content):
            logger.warning(f"[segments] locked write failed: {_STORE}")
    except Exception as e:
        # Fallback: simple rewrite — never raise.
        try:
            os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
            with open(_STORE, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        except Exception as e2:
            logger.warning(f"[segments] write failed: {e} / {e2}")


# --------------------------- condition matching --------------------------- #
def _coerce_num(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def _field_value(record: dict[str, Any], field: str) -> Any:
    """Map a logical field name to the REAL value on a pool record."""
    if field == "lead_score":
        # prospect_lists.search() puts the live score under `score`.
        return record.get("score", record.get("lead_score", 0))
    if field == "has_email":
        return "@" in str(record.get("email") or "")
    return record.get(field)


def _apply_op(actual: Any, op: str, expected: Any) -> bool:
    """Single (field, op, value) check. Never raise — bad op/type = False."""
    try:
        if op == "exists":
            # truthy expected => must be present/truthy; falsy => must be absent/empty.
            present = actual not in (None, "", [], {})
            want = (
                expected
                if isinstance(expected, bool)
                else str(expected).lower()
                not in (
                    "false",
                    "0",
                    "no",
                    "",
                )
            )
            return present if want else (not present)

        if op == "in":
            # expected is a list (or comma string) — actual must be one of them.
            opts: list[Any]
            if isinstance(expected, (list, tuple, set)):
                opts = list(expected)
            else:
                opts = [s.strip() for s in str(expected).split(",") if s.strip()]
            a = str(actual).strip().lower()
            return any(a == str(o).strip().lower() for o in opts)

        if op == "contains":
            return str(expected).strip().lower() in str(actual or "").lower()

        if op in ("eq", "ne"):
            # bool-aware compare
            if isinstance(actual, bool) or isinstance(expected, bool):
                a = bool(actual)
                e = (
                    expected
                    if isinstance(expected, bool)
                    else str(expected).lower()
                    in (
                        "true",
                        "1",
                        "yes",
                    )
                )
                return (a == e) if op == "eq" else (a != e)
            na, ne = _coerce_num(actual), _coerce_num(expected)
            if na is not None and ne is not None:
                return (na == ne) if op == "eq" else (na != ne)
            same = str(actual).strip().lower() == str(expected).strip().lower()
            return same if op == "eq" else (not same)

        if op in ("gt", "gte", "lt", "lte"):
            na, ne = _coerce_num(actual), _coerce_num(expected)
            if na is None or ne is None:
                return False
            if op == "gt":
                return na > ne
            if op == "gte":
                return na >= ne
            if op == "lt":
                return na < ne
            return na <= ne
    except Exception:
        return False
    return False


def _match_record(
    record: dict[str, Any],
    conditions: list[dict[str, Any]],
    match_mode: str = "all",
) -> bool:
    """PURE helper — does `record` satisfy `conditions` under all/any mode?

    Empty conditions => match everyone (segment = whole pool). Never raise.
    This is the unit-test target.
    """
    try:
        conds = [c for c in (conditions or []) if isinstance(c, dict) and c.get("field")]
        if not conds:
            return True
        results: list[bool] = []
        for c in conds:
            field = str(c.get("field"))
            op = str(c.get("op") or "eq").lower()
            expected = c.get("value")
            actual = _field_value(record, field)
            results.append(_apply_op(actual, op, expected))
        if str(match_mode).lower() == "any":
            return any(results)
        return all(results)
    except Exception:
        return False


# --------------------------- CRUD --------------------------- #
def _norm_conditions(conditions: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in conditions or []:
        try:
            field = str(c.get("field") or "").strip()
            if not field:
                continue
            op = str(c.get("op") or "eq").strip().lower()
            if op not in SUPPORTED_OPS:
                op = "eq"
            out.append({"field": field, "op": op, "value": c.get("value")})
        except Exception:
            continue
    return out


def create_segment(
    name: str, match: str = "all", conditions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """New dynamic segment. Kabhi raise nahi."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        rec = {
            "id": uuid.uuid4().hex[:10],
            "name": (str(name).strip() or "segment")[:80],
            "match": "any" if str(match).lower() == "any" else "all",
            "conditions": _norm_conditions(conditions),
            "created_at": now,
            "updated_at": now,
        }
        rows = _read_all()
        rows.append(rec)
        _write_all(rows)
        return rec
    except Exception as e:
        logger.warning(f"[segments] create failed: {e}")
        return {"id": "", "name": str(name), "match": match, "conditions": [], "error": str(e)}


def list_segments() -> list[dict[str, Any]]:
    """Newest-first. Kabhi raise nahi."""
    try:
        return _read_all()[::-1]
    except Exception:
        return []


def get_segment(segment_id: str) -> dict[str, Any] | None:
    try:
        for r in _read_all():
            if r.get("id") == segment_id:
                return r
        return None
    except Exception:
        return None


def delete_segment(segment_id: str) -> bool:
    try:
        rows = _read_all()
        kept = [r for r in rows if r.get("id") != segment_id]
        if len(kept) == len(rows):
            return False
        _write_all(kept)
        return True
    except Exception as e:
        logger.warning(f"[segments] delete failed: {e}")
        return False


# --------------------------- evaluation --------------------------- #
def _load_pool(limit: int = 500) -> list[dict[str, Any]]:
    """REUSE the existing prospect/lead loader (prospect_lists.search) —
    no new data source. Returns scored prospector records. Kabhi raise nahi."""
    try:
        from app.platform import prospect_lists

        # Unfiltered pull (segment conditions do the real filtering); cap big.
        return prospect_lists.search(limit=max(1, min(int(limit), 500)))
    except Exception as e:
        logger.warning(f"[segments] pool load failed: {e}")
        return []


def evaluate(segment: dict[str, Any], limit: int = 500) -> dict[str, Any]:
    """Live-evaluate a segment against the reused pool.

    Returns {count, sample: [...first 50...], matched_ids: [...]}. Kabhi raise nahi.
    """
    try:
        conditions = (segment or {}).get("conditions") or []
        match_mode = (segment or {}).get("match") or "all"
        pool = _load_pool(limit=limit)
        matched: list[dict[str, Any]] = []
        for rec in pool:
            if _match_record(rec, conditions, match_mode):
                matched.append(rec)
        matched_ids = [str(r.get("id")) for r in matched if r.get("id")]
        sample = []
        for r in matched[:50]:
            sample.append(
                {
                    "id": r.get("id"),
                    "business_name": r.get("business_name"),
                    "niche": r.get("niche"),
                    "city": r.get("city"),
                    "status": r.get("status") or "ready",
                    "source": r.get("source"),
                    "lead_score": r.get("score", r.get("lead_score", 0)),
                    "has_email": "@" in str(r.get("email") or ""),
                    "email": r.get("email"),
                }
            )
        return {"count": len(matched), "sample": sample, "matched_ids": matched_ids}
    except Exception as e:
        logger.warning(f"[segments] evaluate failed: {e}")
        return {"count": 0, "sample": [], "matched_ids": [], "error": str(e)}
