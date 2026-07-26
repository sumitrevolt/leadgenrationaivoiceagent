"""Durable-enough mission store (repo-native JSON files, no new dependency).

Mirrors the `delivery_ledger` pattern already used in this repo: one JSON
document per mission plus an append-only event log, written atomically via
``os.replace``. A process-wide lock serialises read-modify-write so lease
acquisition is a real compare-and-set within one worker; cross-process file
ownership still uses the existing Redis-backed ``app.dev_control.locks``.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.dev_control.external_agents.policy import redact
from app.dev_control.external_agents.schema import TERMINAL_STATES, Mission, MissionState

DEFAULT_ROOT = "data/external_missions"
_MUTEX = threading.RLock()


def _root() -> Path:
    return Path(os.getenv("EXTERNAL_MISSION_DIR") or DEFAULT_ROOT)


def _mission_path(mission_id: str) -> Path:
    safe = "".join(c for c in mission_id if c.isalnum() or c in "-_.")[:80]
    return _root() / f"{safe}.json"


def _events_path() -> Path:
    return _root() / "events.jsonl"


def _index_path() -> Path:
    return _root() / "idempotency.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):  # pragma: no cover - replace already moved it
            os.unlink(tmp)


def record_event(mission_id: str, event: str, detail: Any = None) -> None:
    """Append one redacted audit line. Never raises into the caller."""
    try:
        line = json.dumps(
            {
                "at": datetime.utcnow().isoformat(),
                "mission_id": mission_id,
                "event": event,
                "detail": redact(detail),
            },
            ensure_ascii=False,
        )
        p = _events_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def save(mission: Mission) -> Mission:
    with _MUTEX:
        mission.validate()
        _atomic_write(
            _mission_path(mission.mission_id),
            json.dumps(mission.to_dict(), ensure_ascii=False, indent=2),
        )
    return mission


def get(mission_id: str) -> Mission | None:
    path = _mission_path(mission_id)
    if not path.exists():
        return None
    try:
        return Mission.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def list_missions(
    *, status: str | None = None, executor: str | None = None, limit: int = 200
) -> list[Mission]:
    root = _root()
    if not root.exists():
        return []
    out: list[Mission] = []
    for path in sorted(root.glob("msn_*.json")):
        try:
            m = Mission.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if status and m.status.value != status:
            continue
        if executor and m.executor.lower() != executor.lower():
            continue
        out.append(m)
    out.sort(key=lambda m: (m.updated_at or ""), reverse=True)
    return out[: max(1, limit)]


# ---------------- idempotency ----------------


def _load_index() -> dict[str, str]:
    path = _index_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def find_by_idempotency_key(key: str) -> Mission | None:
    mission_id = _load_index().get((key or "").strip())
    return get(mission_id) if mission_id else None


def register_idempotency(key: str, mission_id: str) -> None:
    with _MUTEX:
        index = _load_index()
        index[(key or "").strip()] = mission_id
        _atomic_write(_index_path(), json.dumps(index, ensure_ascii=False, indent=2))


# ---------------- leases ----------------


def claim(
    mission_id: str, owner: str, *, ttl_s: int = 900, now: datetime | None = None
) -> dict[str, Any]:
    """Compare-and-set lease acquisition. Only one owner can win."""
    with _MUTEX:
        mission = get(mission_id)
        if mission is None:
            return {"claimed": False, "reason": "mission_not_found"}
        if mission.status in TERMINAL_STATES:
            return {"claimed": False, "reason": "mission_terminal", "status": mission.status.value}
        if mission.lease_active(now) and mission.lease_owner != owner:
            return {"claimed": False, "reason": "lease_held", "lease_owner": mission.lease_owner}
        mission.set_lease(owner, ttl_s, now)
        save(mission)
        record_event(mission_id, "lease_claimed", {"owner": owner, "ttl_s": ttl_s})
        return {"claimed": True, "mission": mission}


def heartbeat(
    mission_id: str, owner: str, *, ttl_s: int = 900, now: datetime | None = None
) -> bool:
    """Extend only a lease the caller owns; steals return False."""
    with _MUTEX:
        mission = get(mission_id)
        if mission is None or mission.lease_owner != owner or not mission.lease_active(now):
            return False
        mission.set_lease(owner, ttl_s, now)
        save(mission)
        return True


def release(mission_id: str, owner: str) -> bool:
    with _MUTEX:
        mission = get(mission_id)
        if mission is None or mission.lease_owner != owner:
            return False
        mission.clear_lease()
        save(mission)
        record_event(mission_id, "lease_released", {"owner": owner})
        return True


def recover_stale(*, now: datetime | None = None) -> list[dict[str, Any]]:
    """Reclaim missions whose worker died: expired lease + in-flight status."""
    recovered: list[dict[str, Any]] = []
    in_flight = {MissionState.CLAIMED, MissionState.RUNNING, MissionState.TESTING}
    with _MUTEX:
        for mission in list_missions(limit=1000):
            if mission.status not in in_flight or mission.lease_active(now):
                continue
            previous = mission.status.value
            mission.clear_lease()
            mission.transition(MissionState.FAILED_RETRYABLE)
            mission.blocker = f"stale_lease_recovered_from:{previous}"
            mission.add_evidence(
                "recovery", {"from": previous}, note="lease expired; worker presumed dead"
            )
            save(mission)
            record_event(mission.mission_id, "stale_lease_recovered", {"from": previous})
            recovered.append({"mission_id": mission.mission_id, "from": previous})
    return recovered
