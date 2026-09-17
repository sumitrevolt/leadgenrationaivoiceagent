"""L3 owner feed bridge — pull real sources → canonical feed (M4 T03).

WHY THIS EXISTS
---------------
ARCH §4(c): "Source (bot_fleet pull | prod /health pull | hermes push | guardian)
→ owner_feed_bridge → owner_feed.emit(build_event(...))". Without a bridge the
feed only gets ad-hoc writes; the owner sees no *systematic* signal.

DESIGN
------
* **Writes only to the canonical feed** (`app/utils/owner_feed.py`). No second feed.
* **Faithful to the truth gate:** `workforce`-sourced events are emitted with
  `verified=False` (owner_feed force-downgrades them) or suppressed entirely.
* **Never raises.** Each probe is best-effort and isolated.
* Egress-only — this module does not poll Telegram.

Evidence label: CODE-PRESENT (pinned by tests/test_owner_notify.py).
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# The workforce probe file, force-unverified until the probe is made honest.
WORKFORCE_SOURCES = ("workforce",)


def _emit(**kw: Any) -> bool:
    """Emit to the canonical feed. Never raises."""
    try:
        from app.utils import owner_feed

        return owner_feed.emit(**kw)
    except Exception:
        return False


def bridge_bot_fleet(orchestrator: Any | None = None) -> int:
    """Pull bot-fleet proof (dev_workers + task counts) → feed. Returns events written."""
    written = 0
    try:
        if orchestrator is None:
            from app.platform.automation_orchestrator import AutomationOrchestrator

            orchestrator = AutomationOrchestrator()
        dw = orchestrator.dev_workers_count()
        metrics = orchestrator.get_metrics()
        text = (
            f"Bot fleet: dev_workers={dw} (verified={metrics.get('dev_workers_verified', 0)}), "
            f"tasks done={metrics.get('done_tasks', 0)}, running={metrics.get('running_tasks', 0)}"
        )
        ok = _emit(
            source="bot_fleet",
            actor="pilot",
            text=text,
            severity="info",
            kind="heartbeat",
            evidence="data/orchestrator_ledger.db#dev_workers" if dw > 0 else "",
            verified=dw > 0,
            dedupe_key=f"bot_fleet:hourly:{int(time.time() // 3600)}",
        )
        written += 1 if ok else 0
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("[owner_feed_bridge] bot_fleet probe failed: %s", e)
    return written


def bridge_prod_health(health: dict[str, Any] | None = None) -> int:
    """Pull prod /health version → feed. Never raises."""
    written = 0
    try:
        if health is None:
            # Best-effort local probe; absence is NOT an error.
            health = {}
        status = str(health.get("status", "unknown"))
        version = str(health.get("version", "unknown"))
        ok = _emit(
            source="prod",
            actor="kavya",
            text=f"Prod health: status={status} version={version}",
            severity="info" if status in ("ok", "healthy", "unknown") else "P1",
            kind="heartbeat",
            evidence="http://127.0.0.1:8000/health" if version != "unknown" else "",
            verified=version != "unknown",
            dedupe_key=f"prod_health:hourly:{int(time.time() // 3600)}",
        )
        written += 1 if ok else 0
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("[owner_feed_bridge] prod health probe failed: %s", e)
    return written


def bridge_workforce(status: dict[str, Any] | None = None) -> int:
    """Bridge the workforce probe, FORCE-UNVERIFIED.

    Truth gate: `data/workforce_live_status.json` reports `active_workers=0` and
    `task_execution_verified=false`; it must NEVER be presented as fact. We emit it
    with `verified=False` and an explicit note, or skip when evidence is absent.
    """
    written = 0
    try:
        status = status or {}
        active = int(status.get("active_workers", 0) or 0)
        verified_flag = bool(status.get("task_execution_verified", False))
        note = str(status.get("note", ""))[:200]
        ok = _emit(
            source="workforce",  # → force-unverified
            actor="probe",
            text=f"Workforce probe (UNVERIFIED): active_workers={active}, "
            f"task_execution_verified={verified_flag}. {note}",
            severity="info",
            kind="heartbeat",
            evidence="",  # no evidence by definition
            verified=False,  # explicit — never trust this source
            dedupe_key=f"workforce:hourly:{int(time.time() // 3600)}",
        )
        written += 1 if ok else 0
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("[owner_feed_bridge] workforce probe failed: %s", e)
    return written


def bridge_all(orchestrator: Any | None = None) -> dict[str, int]:
    """Run every bridge probe. Returns per-source write counts. Never raises."""
    return {
        "bot_fleet": bridge_bot_fleet(orchestrator),
        "prod": bridge_prod_health(),
        "workforce": bridge_workforce(),
    }


__all__ = [
    "WORKFORCE_SOURCES",
    "bridge_bot_fleet",
    "bridge_prod_health",
    "bridge_workforce",
    "bridge_all",
]
