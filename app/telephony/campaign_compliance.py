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
from datetime import datetime, time, timedelta


def call_type_for(transactional: bool) -> str:
    return "transactional" if transactional else "promotional"


def trai_window_ok(transactional: bool, now_utc: datetime | None = None) -> tuple[bool, str]:
    """(ok, reason) — IST calling-window check for promotional/transactional calls.

    Uses the SAME single source of truth as the per-call ComplianceGate._window
    (app/telephony/compliance.py): effective_promo_window() for promotional
    (minute-accurate + TRAI-clamped), COMPLIANCE_TXN_START/END for transactional.
    Hour-only logic here previously BLOCKED the tail of a 10:00–19:30 window
    (19:00–19:30 calls rejected) while the per-call gate allowed them. Never raises."""
    try:
        from app.telephony.compliance import _parse_hhmm, effective_promo_window

        ist = (now_utc or datetime.utcnow()) + timedelta(hours=5, minutes=30)
        if transactional:
            start_t = _parse_hhmm(os.environ.get("COMPLIANCE_TXN_START", ""), time(9, 0))
            end_t = _parse_hhmm(os.environ.get("COMPLIANCE_TXN_END", ""), time(21, 0))
        else:
            start_s, end_s = effective_promo_window()
            start_t = _parse_hhmm(start_s, time(9, 0))
            end_t = _parse_hhmm(end_s, time(19, 0))
        now_t = ist.time()
        if start_t <= now_t < end_t:
            return True, ""
        return False, (
            f"TRAI window CLOSED (IST {ist.strftime('%H:%M')}) — allowed "
            f"{start_t.strftime('%H:%M')}-{end_t.strftime('%H:%M')} IST for "
            f"{call_type_for(transactional)}"
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
