"""
Admin DB Explorer API  (Supabase-Studio-style admin backend, on OUR Postgres)
============================================================================
Council decision 2026-06-25: Supabase ko second source-of-truth NAHI banaya
(auto-pause/500MB/free-tier + data fragmentation). Iske badle existing VPS
Postgres ke upar ek READ-ONLY admin data explorer — Studio jaisa "browse any
table" power, bina naya DB, bina naye dependency, single source-of-truth intact.

  GET /api/admin/db/tables                 → saari tables + column-count
  GET /api/admin/db/table/{name}           → paginated rows (read-only, redacted)
  GET /api/admin/db/table/{name}/export.csv → CSV export (read-only, capped)

Safety:
  * Flag-gated: ``ADMIN_DB_EXPLORER=1`` warna 503 (INERT default).
  * Super-admin only (raw DB = highest privilege).
  * READ-ONLY — koi INSERT/UPDATE/DELETE endpoint nahi.
  * SQL-injection-safe: table/column identifiers DB-introspection list ke against
    validate + dialect quote; LIMIT/OFFSET integer-clamped; params bind.
  * Sensitive columns (password/hash/secret/token/key…) auto-redact.
  * Never raises raw — clean errors; blocking DB work ``asyncio.to_thread`` me.
"""

from __future__ import annotations

import asyncio
import csv
import io
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.auth_deps import require_super_admin

router = APIRouter(prefix="/api/admin/db", tags=["Admin DB Explorer"])

# Column-name substrings jinki value kabhi UI me dikhani nahi (security-first;
# thoda over-redact better than leaking a secret on screen/screenshot/log).
_SENSITIVE_SUBSTR = (
    "password",
    "passwd",
    "secret",
    "token",
    "hash",
    "salt",
    "api_key",
    "apikey",
    "private",
    "jwt",
    "otp",
    "totp",
    "dsn",
    "credential",
    "signing",
    "webhook_sig",
)

_DEFAULT_PAGE = 50
_MAX_PAGE = 500
_MAX_EXPORT = 5000


def _enabled() -> bool:
    return (os.getenv("ADMIN_DB_EXPLORER", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _guard() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=503,
            detail="ADMIN_DB_EXPLORER disabled — .env me ADMIN_DB_EXPLORER=1 set karo",
        )


def _is_sensitive(col: str) -> bool:
    c = (col or "").lower()
    return any(s in c for s in _SENSITIVE_SUBSTR)


def _jsonable(v: object) -> object:
    """DB value → JSON-safe scalar (never raises)."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (bytes, bytearray, memoryview)):
        try:
            return f"<binary {len(bytes(v))} bytes>"
        except Exception:
            return "<binary>"
    try:
        import datetime as _dt
        import decimal as _dec
        import uuid as _uuid

        if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
            return v.isoformat()
        if isinstance(v, _dec.Decimal):
            return float(v)
        if isinstance(v, _uuid.UUID):
            return str(v)
    except Exception:
        pass
    try:
        return str(v)
    except Exception:
        return "<unprintable>"


def _engine():
    """Existing SYNC SQLAlchemy engine (PgBouncer/Postgres; sqlite in tests)."""
    try:
        from app.models import base as _b

        return _b._get_sync_engine()
    except Exception:
        return None


def _list_tables() -> dict:
    """Sab tables + column-count (cheap; per-table row COUNT(*) yahan NAHI)."""
    eng = _engine()
    if eng is None:
        return {"available": False, "reason": "no_engine", "tables": [], "count": 0}
    try:
        from sqlalchemy import inspect as sa_inspect

        insp = sa_inspect(eng)
        names = sorted(insp.get_table_names())
        out: list[dict] = []
        for n in names:
            try:
                cols = insp.get_columns(n)
            except Exception:
                cols = []
            out.append({"table": n, "columns": len(cols)})
        return {
            "available": True,
            "dialect": eng.dialect.name,
            "tables": out,
            "count": len(out),
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)[:160], "tables": [], "count": 0}


def _read_table(
    name: str,
    limit: int,
    offset: int,
    order_by: str | None,
    descending: bool,
    want_count: bool,
) -> dict:
    """Paginated read-only rows from ONE validated table; sensitive cols redacted."""
    eng = _engine()
    if eng is None:
        return {"status": 503, "error": "database engine unavailable"}
    try:
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy import text as sa_text

        insp = sa_inspect(eng)
        if name not in set(insp.get_table_names()):
            return {"status": 404, "error": f"table not found: {name}"}

        cols_meta = insp.get_columns(name)
        col_names = [c["name"] for c in cols_meta]

        prep = eng.dialect.identifier_preparer
        qtable = prep.quote(name)

        lim = max(1, min(int(limit or _DEFAULT_PAGE), _MAX_PAGE))
        off = max(0, int(offset or 0))

        order_sql = ""
        if order_by and order_by in col_names:
            order_sql = f" ORDER BY {prep.quote(order_by)} {'DESC' if descending else 'ASC'}"

        sql = f"SELECT * FROM {qtable}{order_sql} LIMIT :_lim OFFSET :_off"  # noqa: S608 (identifiers validated+quoted)

        total: int | None = None
        with eng.connect() as conn:
            result = conn.execute(sa_text(sql), {"_lim": lim, "_off": off})
            mapped = result.mappings().all()
            if want_count:
                try:
                    total = conn.execute(
                        sa_text(f"SELECT COUNT(*) FROM {qtable}")  # noqa: S608
                    ).scalar()
                except Exception:
                    total = None

        sensitive = sorted({c for c in col_names if _is_sensitive(c)})
        sens_set = set(sensitive)
        rows: list[dict] = []
        for m in mapped:
            row: dict = {}
            for k, v in m.items():
                if k in sens_set:
                    row[k] = "***redacted***" if v is not None else None
                else:
                    row[k] = _jsonable(v)
            rows.append(row)

        return {
            "table": name,
            "columns": col_names,
            "sensitive": sensitive,
            "rows": rows,
            "returned": len(rows),
            "limit": lim,
            "offset": off,
            "total": total,
            "read_only": True,
        }
    except Exception as exc:
        return {"status": 500, "error": str(exc)[:200]}


def _export_csv(name: str, limit: int, order_by: str | None, descending: bool) -> dict:
    """Build a redacted CSV (capped) for ONE table; returns {csv|error}."""
    res = _read_table(
        name, max(1, min(int(limit or 1000), _MAX_EXPORT)), 0, order_by, descending, False
    )
    if res.get("status"):
        return res
    buf = io.StringIO()
    writer = csv.writer(buf)
    cols = res.get("columns") or []
    writer.writerow(cols)
    for row in res.get("rows") or []:
        writer.writerow(["" if row.get(c) is None else row.get(c) for c in cols])
    return {"csv": buf.getvalue(), "rows": res.get("returned", 0)}


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/tables", summary="List all DB tables (read-only explorer)")
async def list_tables(_user=Depends(require_super_admin)):
    _guard()
    return await asyncio.to_thread(_list_tables)


@router.get("/table/{name}", summary="Browse rows of one table (read-only, paginated, redacted)")
async def read_table(
    name: str,
    limit: int = _DEFAULT_PAGE,
    offset: int = 0,
    order_by: str = "",
    desc: bool = True,
    count: bool = True,
    _user=Depends(require_super_admin),
):
    _guard()
    res = await asyncio.to_thread(_read_table, name, limit, offset, order_by or None, desc, count)
    status = res.get("status")
    if status:
        raise HTTPException(status_code=int(status), detail=res.get("error", "error"))
    return res


@router.get(
    "/table/{name}/export.csv", summary="Export one table to CSV (read-only, capped, redacted)"
)
async def export_table(
    name: str,
    limit: int = 1000,
    order_by: str = "",
    desc: bool = True,
    _user=Depends(require_super_admin),
):
    _guard()
    res = await asyncio.to_thread(_export_csv, name, limit, order_by or None, desc)
    status = res.get("status")
    if status:
        raise HTTPException(status_code=int(status), detail=res.get("error", "error"))
    safe_name = "".join(ch for ch in name if ch.isalnum() or ch in ("_", "-")) or "table"
    return Response(
        content=res.get("csv", ""),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'},
    )
