"""Mission persistence with cross-process CAS as the correctness boundary.

JSON documents under ``EXTERNAL_MISSION_DIR`` (default ``data/external_missions``)
are the payload store. Production VPS containers share ``./data:/app/data``, so
the directory is visible to app/worker/scheduler. Lease claim, idempotency
registration and document mutation are serialised by ``cas.get_backend()``
(Redis when reachable, else portalocker file locks) — never by a process-local
mutex alone.

Topology facts (verified against ``docker-compose.vps.yml``):
  * ``./data`` is bind-mounted into app, worker, scheduler, worker-heavy,
    worker-video — so FileLock CAS on ``data/external_missions/.locks/`` is
    shared across those containers on one VPS host.
  * Redis (``REDIS_URL``) is the preferred multi-container CAS backend when
    reachable; same pattern as ``dev_control.locks.RedisOwnershipLock``.
  * A Windows Cursor session and a Claude Code session only share state when
    they point at the same ``EXTERNAL_MISSION_DIR`` (or the same Redis).
  * Redeploy preserves ``./data``; container replacement does not wipe the
    mission store. JSON alone without the CAS backend is NOT distributed-safe.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.dev_control.external_agents import cas as cas_mod
from app.dev_control.external_agents.policy import redact
from app.dev_control.external_agents.schema import TERMINAL_STATES, Mission, MissionState

# Local optimisation only — held INSIDE an already-acquired CAS lock.
_LOCAL = threading.RLock()


def _root() -> Path:
    """Mission store root — EXTERNAL_MISSION_DIR override, else shared authority."""
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="devcontrol.external_missions",
        legacy_path=Path("data") / "external_missions",
        target_segments=("external_missions",),
        override_env="EXTERNAL_MISSION_DIR",
    )


def _mission_path(mission_id: str) -> Path:
    safe = "".join(c for c in mission_id if c.isalnum() or c in "-_.")[:80]
    return _root() / f"{safe}.json"


def _events_path() -> Path:
    return _root() / "events.jsonl"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):  # pragma: no cover
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
    backend = cas_mod.get_backend(root=str(_root()))

    def _write() -> Mission:
        with _LOCAL:
            mission.validate()
            payload = mission.to_dict()
            payload["cas_version"] = int(payload.get("cas_version") or 0) + 1
            # Reflect the bumped version back onto the object for subsequent CAS.
            if hasattr(mission, "cas_version"):
                mission.cas_version = payload["cas_version"]  # type: ignore[attr-defined]
            else:
                # Missions created before the field existed — stamp via dict roundtrip.
                mission.__dict__["cas_version"] = payload["cas_version"]
            _atomic_write(
                _mission_path(mission.mission_id),
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            return mission

    return backend.with_mission_lock(mission.mission_id, _write)


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
    out.sort(key=lambda m: m.updated_at or "", reverse=True)
    return out[: max(1, limit)]


# ---------------- idempotency ----------------


def find_by_idempotency_key(key: str) -> Mission | None:
    backend = cas_mod.get_backend(root=str(_root()))
    mission_id = backend.get_idempotency((key or "").strip())
    return get(mission_id) if mission_id else None


def register_idempotency(key: str, mission_id: str) -> dict[str, Any]:
    """Atomic first-writer-wins registration across processes."""
    backend = cas_mod.get_backend(root=str(_root()))
    return backend.register_idempotency((key or "").strip(), mission_id)


# ---------------- leases ----------------


def _utc_epoch(dt: datetime) -> float:
    """Epoch seconds for a NAIVE datetime that holds UTC wall-clock.

    `dt.timestamp()` on a naive datetime asks the OS to interpret it as LOCAL
    time. Everything in this module produces naive UTC (`datetime.utcnow()`), so
    calling `.timestamp()` on that value shifts every lease window by the host's
    UTC offset — five and a half hours on the IST hosts this project runs on,
    which put `lease_expiry` in the PAST the moment a lease was taken.

    Why it survived: the CAS backend compares `cur.until > now` with both sides
    coming from the same shifted call, so the layer that would have caught the
    error shared it. What broke was `Mission.lease_active()`, which compares the
    rendered `lease_expiry` against a correct `utcnow()` — and therefore reported
    every live lease as expired, inviting a second runner to claim a mission that
    was still executing.
    """
    return dt.replace(tzinfo=timezone.utc).timestamp()


def _apply_lease_to_mission(mission: Mission, owner: str, until: float) -> None:
    mission.lease_owner = owner
    mission.lease_expiry = datetime.utcfromtimestamp(until).isoformat()
    mission.last_heartbeat = datetime.utcnow().isoformat()
    mission.updated_at = mission.last_heartbeat


def claim(
    mission_id: str, owner: str, *, ttl_s: int = 900, now: datetime | None = None
) -> dict[str, Any]:
    """Cross-process compare-and-set lease. Exactly one owner can win."""
    try:
        backend = cas_mod.get_backend(root=str(_root()))
    except cas_mod.CasBackendError as exc:
        return {"claimed": False, "reason": str(exc), "backend": "unavailable"}
    now_dt = now or datetime.utcnow()
    now_ts = _utc_epoch(now_dt)

    def _body() -> dict[str, Any]:
        mission = get(mission_id)
        if mission is None:
            return {"claimed": False, "reason": "mission_not_found"}
        if mission.status in TERMINAL_STATES:
            return {
                "claimed": False,
                "reason": "mission_terminal",
                "status": mission.status.value,
            }
        result = backend.claim_lease(mission_id, owner, ttl_s=ttl_s, now=now_ts)
        if not result.get("claimed"):
            return result
        _apply_lease_to_mission(mission, owner, float(result["until"]))
        # Persist under the same mission doc lock we already hold.
        with _LOCAL:
            mission.validate()
            _atomic_write(
                _mission_path(mission.mission_id),
                json.dumps(mission.to_dict(), ensure_ascii=False, indent=2),
            )
        record_event(
            mission_id, "lease_claimed", {"owner": owner, "ttl_s": ttl_s, "backend": backend.name}
        )
        return {"claimed": True, "mission": mission, "backend": backend.name}

    return backend.with_mission_lock(mission_id, _body)


def heartbeat(
    mission_id: str, owner: str, *, ttl_s: int = 900, now: datetime | None = None
) -> bool:
    backend = cas_mod.get_backend(root=str(_root()))
    now_dt = now or datetime.utcnow()
    if not backend.heartbeat_lease(mission_id, owner, ttl_s=ttl_s, now=_utc_epoch(now_dt)):
        return False

    def _body() -> bool:
        mission = get(mission_id)
        if mission is None or mission.lease_owner != owner:
            return False
        _apply_lease_to_mission(mission, owner, _utc_epoch(now_dt) + max(1, int(ttl_s)))
        with _LOCAL:
            _atomic_write(
                _mission_path(mission.mission_id),
                json.dumps(mission.to_dict(), ensure_ascii=False, indent=2),
            )
        return True

    return bool(backend.with_mission_lock(mission_id, _body))


def release(mission_id: str, owner: str) -> bool:
    backend = cas_mod.get_backend(root=str(_root()))
    if not backend.release_lease(mission_id, owner):
        return False

    def _body() -> bool:
        mission = get(mission_id)
        if mission is None:
            return False
        mission.clear_lease()
        with _LOCAL:
            _atomic_write(
                _mission_path(mission.mission_id),
                json.dumps(mission.to_dict(), ensure_ascii=False, indent=2),
            )
        record_event(mission_id, "lease_released", {"owner": owner, "backend": backend.name})
        return True

    return bool(backend.with_mission_lock(mission_id, _body))


def transition_cas(
    mission_id: str,
    expected_status: MissionState | str,
    target: MissionState,
    *,
    mutate: Any = None,
) -> dict[str, Any]:
    """Compare-and-set state transition. Stale writers are rejected."""

    def _body(mission: Mission) -> None:
        mission.transition(target)
        if mutate:
            mutate(mission)

    return apply_cas(mission_id, expected_status=expected_status, mutate=_body)


def apply_cas(
    mission_id: str,
    *,
    expected_status: MissionState | str | None = None,
    mutate: Any,
) -> dict[str, Any]:
    """Load + mutate + save under the mission doc lock.

    This is the production correctness boundary for orchestrator lifecycle
    mutations. ``cas_version`` is an audit counter bumped under the same lock —
    the lock (not optimistic versioning) prevents lost updates. Stale writers
    that pass an ``expected_status`` are rejected with ``stale_transition``.
    """
    backend = cas_mod.get_backend(root=str(_root()))
    expected: MissionState | None = None
    if expected_status is not None:
        expected = (
            expected_status
            if isinstance(expected_status, MissionState)
            else MissionState(expected_status)
        )

    def _body() -> dict[str, Any]:
        mission = get(mission_id)
        if mission is None:
            return {"ok": False, "reason": "mission_not_found"}
        if expected is not None and mission.status is not expected:
            return {
                "ok": False,
                "reason": "stale_transition",
                "current": mission.status.value,
                "expected": expected.value,
            }
        try:
            mutate(mission)
        except Exception as exc:  # InvalidMissionTransition / LeaseError / etc.
            return {"ok": False, "reason": str(exc)}
        with _LOCAL:
            mission.validate()
            payload = mission.to_dict()
            payload["cas_version"] = int(payload.get("cas_version") or 0) + 1
            mission.__dict__["cas_version"] = payload["cas_version"]
            mission.updated_at = datetime.utcnow().isoformat()
            payload["updated_at"] = mission.updated_at
            _atomic_write(
                _mission_path(mission.mission_id),
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        record_event(
            mission_id,
            "apply_cas",
            {
                "status": mission.status.value,
                "backend": backend.name,
                "cas_version": payload["cas_version"],
            },
        )
        return {"ok": True, "mission": mission}

    return backend.with_mission_lock(mission_id, _body)


def recover_stale(*, now: datetime | None = None) -> list[dict[str, Any]]:
    """Reclaim missions whose worker died: expired lease + in-flight status."""
    backend = cas_mod.get_backend(root=str(_root()))
    recovered: list[dict[str, Any]] = []
    in_flight = {MissionState.CLAIMED, MissionState.RUNNING, MissionState.TESTING}
    now_dt = now or datetime.utcnow()
    now_ts = _utc_epoch(now_dt)

    for mission in list_missions(limit=1000):
        if mission.status not in in_flight:
            continue
        lease = backend.get_lease(mission.mission_id)
        # Prefer CAS lease record; fall back to mission document expiry.
        active = False
        if lease is not None:
            active = lease.until > now_ts
        else:
            active = mission.lease_active(now_dt)
        if active:
            continue

        def _recover(
            mid: str = mission.mission_id, prev: str = mission.status.value
        ) -> dict[str, Any]:
            m = get(mid)
            if m is None or m.status not in in_flight:
                return {"ok": False}
            # Re-check lease under the doc lock.
            live = backend.get_lease(mid)
            if live is not None and live.until > now_ts:
                return {"ok": False, "reason": "lease_became_active"}
            m.clear_lease()
            m.transition(MissionState.FAILED_RETRYABLE)
            m.blocker = f"stale_lease_recovered_from:{prev}"
            m.add_evidence("recovery", {"from": prev}, note="lease expired; worker presumed dead")
            with _LOCAL:
                _atomic_write(
                    _mission_path(m.mission_id),
                    json.dumps(m.to_dict(), ensure_ascii=False, indent=2),
                )
            record_event(mid, "stale_lease_recovered", {"from": prev, "backend": backend.name})
            return {"ok": True, "mission_id": mid, "from": prev}

        out = backend.with_mission_lock(mission.mission_id, _recover)
        if out.get("ok"):
            recovered.append({"mission_id": out["mission_id"], "from": out["from"]})
    return recovered


def persistence_report() -> dict[str, Any]:
    """Operator-facing evidence about the store topology."""
    root = _root()
    status = cas_mod.shared_store_status(root=str(root))
    return {
        **status,
        "mission_dir": str(root.resolve()) if root.exists() else str(root),
        "exists": root.exists(),
        "vps_bind_mount": "./data:/app/data (docker-compose.vps.yml) — shared by app/worker/scheduler",
        "survives_redeploy": True,
        "windows_cursor_claude_share": (
            "only if both processes set EXTERNAL_MISSION_DIR to the same path "
            "(or both use the same REDIS_URL)"
        ),
        "correctness_boundary": status["backend"],
        "thread_mutex_is_not_correctness_boundary": True,
    }
