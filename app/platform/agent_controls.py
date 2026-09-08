"""agent_controls.py — real, narrowly-scoped pause/resume for AI staff agents.

Design mirrors approvals_bridge.py's proven sidecar pattern EXACTLY (append-only
jsonl, collapse-to-latest by key, never raises) rather than inventing a new store.

HONEST SCOPE (do not expand without re-reading this docstring):
  team_scheduler.py's `_run_job` wrapper is explicitly documented in its own
  code as behaviour-neutral ("Wrapper KABHI behaviour change nahi karta") — a
  deliberate project invariant. Pausing an agent here does NOT touch the
  scheduler/cron loop at all. It gates exactly one real choke point:
  `app.agents.staff.run_member()` — i.e. the admin-facing "Run now" manual
  trigger. Scheduled/automatic runs of that same job are UNAFFECTED. The UI
  must say so explicitly — a pause control that silently claims to stop all
  automation would be the "lies to admin" failure mode this project forbids.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "agent_pause_state.jsonl")

# job-name aliases in app.agents.staff.run_member()'s dispatch table that
# resolve to the SAME underlying STAFF member — pausing "arjun" must also
# block a call made via the "qa" alias, and vice versa.
ALIAS_TO_MEMBER = {
    "qa": "arjun",
    "trainer": "meera",
    "ops": "kavya",
    "digest": "manager",
    "content": "isha",
    "email_outreach": "rohan",
    "blog": "isha",  # JOB_META/registry canonical owner (was ravi = KNOWN_DRIFT)
    "growth": "manager",
}


def _canon(key: str) -> str:
    k = (key or "").strip().lower()
    return ALIAS_TO_MEMBER.get(k, k)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out


def _state_map() -> dict[str, dict[str, Any]]:
    """Latest pause/resume record per canonical member key."""
    m: dict[str, dict[str, Any]] = {}
    for r in _read_jsonl(_STORE):
        member = _canon(str(r.get("member") or ""))
        if member:
            m[member] = r
    return m


def is_paused(member: str) -> bool:
    try:
        rec = _state_map().get(_canon(member))
        return bool(rec and rec.get("paused"))
    except Exception:
        return False


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("[agent_controls] write skip: %s", e)


def pause(member: str, by: str = "admin", note: str = "") -> dict[str, Any]:
    m = _canon(member)
    if not m:
        return {"ok": False, "error": "member required"}
    rec = {
        "member": m,
        "paused": True,
        "by": (by or "admin")[:80],
        "note": (note or "")[:200],
        "at": _now_iso(),
    }
    _append(rec)
    try:
        from app.platform import team

        team.log_event(
            m, "paused_by_admin", f"Manual run paused by {by}: {note}"[:200], status="warn"
        )
    except Exception:
        pass
    return {"ok": True, **rec}


def resume(member: str, by: str = "admin", note: str = "") -> dict[str, Any]:
    m = _canon(member)
    if not m:
        return {"ok": False, "error": "member required"}
    rec = {
        "member": m,
        "paused": False,
        "by": (by or "admin")[:80],
        "note": (note or "")[:200],
        "at": _now_iso(),
    }
    _append(rec)
    try:
        from app.platform import team

        team.log_event(m, "resumed_by_admin", f"Manual run resumed by {by}", status="ok")
    except Exception:
        pass
    return {"ok": True, **rec}


def list_paused() -> dict[str, dict[str, Any]]:
    """Canonical member key -> latest state record, PAUSED members only."""
    try:
        return {k: v for k, v in _state_map().items() if v.get("paused")}
    except Exception:
        return {}
