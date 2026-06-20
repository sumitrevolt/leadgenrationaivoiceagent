"""Dialer leaderboard — telecaller gamification (NeoDove-style) over dialer_logs.

Kyun: jin clients ke paas khud ke telecallers hain, unke liye daily/weekly
ranking = motivation + visibility ("🏆 Aaj ka top caller"). Data source =
EXISTING `data/dialer_logs.jsonl` (dialer_log.log_disposition likhta — rebuild
NAHI). Records: {phone, disposition, notes, at} (+ optional "caller"/"by" field
— abhi disposition API caller naam nahi leta, isliye unnamed = "Team" bucket;
caller field aate hi leaderboard per-person ho jayega, code ready).

Scoring (pure-python, koi LLM/DB nahi):
  call = +1 · connect (no-answer/wrong-number ke alawa) = +2 · interested = +5
Never raises. Read-only (koi flag nahi).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIALER_LOGS = os.path.join("data", "dialer_logs.jsonl")

_NOT_CONNECTED = ("no-answer", "wrong-number")
_POINTS_CALL = 1
_POINTS_CONNECT = 2
_POINTS_INTERESTED = 5


def _read_logs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_DIALER_LOGS):
            return out
        with open(_DIALER_LOGS, encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[leaderboard] read failed: {e}")
    return out


def _caller_name(rec: dict[str, Any]) -> str:
    return str(rec.get("caller") or rec.get("by") or "Team").strip()[:40] or "Team"


def _parse_at(rec: dict[str, Any]) -> datetime | None:
    try:
        raw = str(rec.get("at") or "")
        if not raw:
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def leaderboard(days: int = 1) -> dict[str, Any]:
    """Per-caller ranking last `days` din ka (1=aaj-tak-24h, 7=weekly). Never raises.

    Returns: {period_days, total_calls, ranking: [{rank, caller, calls, connects,
    interested, callbacks, score}], shoutout}
    """
    try:
        days = max(1, min(int(days or 1), 90))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        per: dict[str, dict[str, int]] = defaultdict(
            lambda: {"calls": 0, "connects": 0, "interested": 0, "callbacks": 0, "score": 0}
        )
        total = 0
        for rec in _read_logs():
            at = _parse_at(rec)
            if at is None or at < cutoff:
                continue
            disp = str(rec.get("disposition") or "").strip().lower()
            if not disp:
                continue
            row = per[_caller_name(rec)]
            total += 1
            row["calls"] += 1
            row["score"] += _POINTS_CALL
            if disp not in _NOT_CONNECTED:
                row["connects"] += 1
                row["score"] += _POINTS_CONNECT
            if disp == "interested":
                row["interested"] += 1
                row["score"] += _POINTS_INTERESTED
            if disp == "callback":
                row["callbacks"] += 1

        ranking = [
            {"caller": name, **vals}
            for name, vals in sorted(
                per.items(),
                key=lambda kv: (kv[1]["score"], kv[1]["interested"], kv[1]["calls"]),
                reverse=True,
            )
        ]
        for i, row in enumerate(ranking, start=1):
            row["rank"] = i

        if ranking:
            top = ranking[0]
            label = "Aaj ka" if days == 1 else f"Pichhle {days} din ka"
            shoutout = (
                f"🏆 {label} top caller: {top['caller']} — {top['calls']} calls, "
                f"{top['interested']} interested ({top['score']} points)! Shabaash! 🎉"
            )
        else:
            shoutout = "Abhi koi calls logged nahi — dialer kholo aur shuru karo! 📞"

        return {
            "period_days": days,
            "total_calls": total,
            "ranking": ranking,
            "shoutout": shoutout,
        }
    except Exception as e:
        logger.warning(f"[leaderboard] failed: {e}")
        return {
            "period_days": days,
            "total_calls": 0,
            "ranking": [],
            "shoutout": "",
            "error": str(e)[:200],
        }


__all__ = ["leaderboard"]
