"""dr_health.py — warm-DR replica health probe (Postgres logical replication).

The audit (F.5) called out "cheap warm-DR" as one of the five genuine
remaining blind spots: a single VPS is a SPOF, and the cheap mitigation that
isn't a second full VPS is Postgres logical replication to a free-tier
managed PG (Neon / Supabase free) or a tiny off-box target.

This module is the OPERATIONAL probe that proves the DR is *tested*, not just
configured. Without it the audit warned: "An untested backup is a maybe-backup."

Configuration (env on the live app, NOT on the DR target):
  DR_REPLICA_URL = postgres://user:pass@neon.tech/dbname  (read-only replica)
  DR_LAG_WARN_S  = 60   (lag above this -> WARN — default 60 sec)
  DR_LAG_FAIL_S  = 600  (lag above this -> FAIL — default 10 min)

What it checks (single SQL round-trip on the REPLICA):
  SELECT now() - pg_last_xact_replay_timestamp() AS lag_interval;
  - lag_interval = how far behind primary the replica is, in seconds.
  - NULL -> replica has caught up (no recent activity) -> OK with note.
  - large interval -> WARN/FAIL banded.

The probe is read-only, idempotent, and cheap (single query). Designed for
inclusion in the SRE engineer agent (Pranav) once DR is live.
"""

from __future__ import annotations

import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_REPLICA_ENV = "DR_REPLICA_URL"


def _replica_url() -> str:
    return os.environ.get(_REPLICA_ENV, "").strip()


def _warn_s() -> float:
    try:
        return float(os.environ.get("DR_LAG_WARN_S", "60") or 60)
    except Exception:
        return 60.0


def _fail_s() -> float:
    try:
        return float(os.environ.get("DR_LAG_FAIL_S", "600") or 600)
    except Exception:
        return 600.0


def configured() -> bool:
    return bool(_replica_url())


def probe() -> dict[str, Any]:
    """Single SQL round-trip on the replica. Always returns a structured dict
    — never raises (callers may be on a hot-path)."""
    url = _replica_url()
    if not url:
        return {
            "configured": False,
            "status": "NEUTRAL",
            "summary": "DR replica not configured (set DR_REPLICA_URL in .env)",
            "ts": int(time.time()),
        }
    try:
        # Prefer psycopg2 (already in project lock); fall back to psycopg if
        # the wheel layout changes on a future rebuild.
        try:
            import psycopg2  # type: ignore

            conn = psycopg2.connect(url, connect_timeout=5)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))"
                    )
                    val = cur.fetchone()[0]
                    lag_s = float(val) if val is not None else None
            finally:
                conn.close()
        except Exception:
            import psycopg  # type: ignore

            with psycopg.connect(url, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))"
                    )
                    val = cur.fetchone()[0]
                    lag_s = float(val) if val is not None else None
    except Exception as exc:
        return {
            "configured": True,
            "status": "FAIL",
            "summary": f"DR replica unreachable: {type(exc).__name__}",
            "error": str(exc)[:200],
            "ts": int(time.time()),
        }

    warn_s = _warn_s()
    fail_s = _fail_s()
    if lag_s is None:
        return {
            "configured": True,
            "status": "OK",
            "lag_s": None,
            "summary": "replica idle (no recent primary activity) — connection healthy",
            "ts": int(time.time()),
        }
    if lag_s >= fail_s:
        status = "FAIL"
        summary = f"DR replica {lag_s:.0f}s behind (>{fail_s:.0f}s = FAIL)"
    elif lag_s >= warn_s:
        status = "WARN"
        summary = f"DR replica {lag_s:.0f}s behind (>{warn_s:.0f}s = WARN)"
    else:
        status = "OK"
        summary = f"DR replica {lag_s:.0f}s behind primary"
    return {
        "configured": True,
        "status": status,
        "lag_s": round(lag_s, 1),
        "warn_threshold_s": warn_s,
        "fail_threshold_s": fail_s,
        "summary": summary,
        "ts": int(time.time()),
    }


__all__ = ["configured", "probe"]
