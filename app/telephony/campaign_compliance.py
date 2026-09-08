"""Outbound-campaign compliance pre-check — single source of truth for the
TRAI calling-window gate used by BOTH ``scripts/fire_calls.py`` (CLI) and the
Celery ``run_campaign_task`` (``app/tasks/calling.py``).

Extracted 2026-07-02 so the durable-Celery campaign path and the existing CLI
path can never drift apart — one function, two callers. This is a pre-check
only (cheap, no network): the AUTHORITATIVE per-call gate is still
``VobizClient.place_call()`` (DND/window/consent), which every individual
call goes through regardless of how it was launched. This helper just avoids
queuing/dialing an entire batch that would all get blocked anyway.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta


def call_type_for(transactional: bool) -> str:
    return "transactional" if transactional else "promotional"


def trai_window_ok(transactional: bool, now_utc: datetime | None = None) -> tuple[bool, str]:
    """(ok, reason) — IST calling-window check for promotional/transactional calls.

    Mirrors TRAI's actual 9am-9pm; env defaults kept conservative (matches
    scripts/fire_calls.py, unchanged). Never raises."""
    try:
        ist = (now_utc or datetime.utcnow()) + timedelta(hours=5, minutes=30)
        trai_start = int(os.environ.get("COMPLIANCE_PROMO_START", "10").split(":")[0])
        trai_end = int(os.environ.get("COMPLIANCE_PROMO_END", "19").split(":")[0])
        txn_end = int(os.environ.get("COMPLIANCE_TXN_END", "21").split(":")[0])
        txn_start = int(os.environ.get("COMPLIANCE_TXN_START", "9").split(":")[0])
        end_hour = txn_end if transactional else trai_end
        start_hour = txn_start if transactional else trai_start
        if start_hour <= ist.hour < end_hour:
            return True, ""
        return False, (
            f"TRAI window CLOSED (IST {ist.hour:02d}:xx) — allowed "
            f"{start_hour:02d}:00-{end_hour:02d}:00 IST for {call_type_for(transactional)}"
        )
    except Exception as e:  # pragma: no cover - defensive, never blocks on our own bug
        return True, f"window-check skipped: {e}"


def readiness_ok() -> tuple[bool, int, list[str]]:
    """(ok, score, actions) — telephony readiness gate (score>=70 required).

    Never raises — a readiness-check failure fails OPEN (score 100) so a bug in
    THIS check can't silently block every campaign; the per-call VobizClient
    gate is still the real backstop."""
    try:
        from app.telephony.telephony_readiness import run_checks

        tr = run_checks()
        score = int(tr.get("score") or 0)
        return score >= 70, score, list(tr.get("actions") or [])
    except Exception:
        return True, 100, []
