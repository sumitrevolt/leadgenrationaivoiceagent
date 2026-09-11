"""video_health.py — end-to-end automation probes for the video system.

WHY THIS EXISTS (do not delete the "ran vs produced" distinction)
-----------------------------------------------------------------
`automation_health` is a LIVENESS dead-man: it records that a job RAN and did
not raise. It cannot tell that the job DID nothing. That blind spot is not
hypothetical — the 2026-08-09 postmortem found `video_ad_cycle` gated inert by a
flag-alias bug for 15 days while every heartbeat stayed green.

So each probe here reports TWO independent things:

  * ``ran``      — a heartbeat exists for the job (from `automation_health`).
  * ``produced`` — an ARTIFACT actually exists AND is fresh.

A probe that only has a heartbeat is **``warn``**, never ``ok``. ``ok`` requires
a real artifact. This is the fake-green fix; collapsing the two back into one
field reintroduces the exact outage this module exists to catch.

TRUTH GATE
----------
``verified`` is True only when an artifact was actually OBSERVED (evidence-backed).
The per-automation event is built through ``app.utils.owner_feed.build_event`` so
the truth gate is applied — a probe that observed nothing cannot label itself
verified. Never raises.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: How long an artifact may sit unchanged before the producer is "stale".
#: The daily producer runs once per day; 30h = one missed day + grace.
STALE_AFTER_S = 30 * 3600

#: Job heartbeat each automation maps to (for the `ran` signal only).
_HEARTBEAT_JOB = {
    "daily_video": "daily_video",
    "local_render": "daily_video",
    "novelty_gate": "daily_video",
    "tg_delivery": "video_delivery",
}


def _on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _now() -> float:
    return time.time()


def _heartbeats() -> dict[str, Any]:
    """Latest-per-job heartbeat snapshot. Cheap; never raises."""
    try:
        from app.platform import automation_health

        beats = automation_health._load_beats()
        return beats if isinstance(beats, dict) else {}
    except Exception:
        return {}


def _newest_mtime(path: str) -> float | None:
    """Newest mtime under a file-or-directory. ``None`` when nothing exists."""
    try:
        if os.path.isfile(path):
            return os.path.getmtime(path)
        if os.path.isdir(path):
            newest: float | None = None
            for root, _dirs, files in os.walk(path):
                for name in files:
                    try:
                        m = os.path.getmtime(os.path.join(root, name))
                    except OSError:
                        continue
                    if newest is None or m > newest:
                        newest = m
            return newest
    except Exception:
        return None
    return None


def _age_s(ts: float | None) -> float | None:
    if ts is None:
        return None
    try:
        return max(0.0, _now() - float(ts))
    except Exception:
        return None


def _verdict(
    automation: str,
    *,
    enabled: bool,
    ran: bool | None,
    produced: bool,
    age_s: float | None,
    detail: dict[str, Any],
    reason_override: str | None = None,
) -> dict[str, Any]:
    """Compute the honest status. `ok` REQUIRES produced (never ran-only).

    ``reason_override`` lets a probe supply a concrete, honest reason (e.g. an
    artifact that is missing on disk). It only wins when the computed status is
    already a problem (``warn``/``down``) — it can never upgrade a gated/ok row.
    """
    stale = (age_s is not None and age_s > STALE_AFTER_S)
    if not enabled:
        status = "gated_inert"
        reason = "flag off — inert"
    elif produced and not stale:
        status = "ok"
        reason = "artifact present and fresh"
    elif produced and stale:
        status = "warn"
        reason = "artifact present but stale"
    elif ran:
        # The fake-green case: the job ran but produced nothing.
        status = "warn"
        reason = "job ran but produced no artifact"
    else:
        status = "down"
        reason = "no heartbeat and no artifact"
    if reason_override and status in ("warn", "down"):
        reason = reason_override
    verified = bool(produced)
    event: dict[str, Any] = {}
    try:
        from app.utils.owner_feed import build_event

        event = build_event(
            source="prod",
            actor="video_health",
            text=f"{automation}: {reason}",
            severity="P0" if status == "down" else ("P1" if status == "warn" else "info"),
            kind="heartbeat",
            evidence=str(detail.get("artifact_path") or ""),
            verified=verified,
        )
    except Exception:
        event = {}
    return {
        "automation": automation,
        "enabled": bool(enabled),
        "ran": ran,
        "produced": bool(produced),
        "stale": bool(stale),
        "artifact_age_s": round(age_s, 1) if isinstance(age_s, (int, float)) else None,
        "verified": verified,
        "status": status,
        "reason": reason,
        "owner_feed": event,
        **detail,
    }


# --------------------------------------------------------------------------- #
# Individual probes
# --------------------------------------------------------------------------- #
def probe_daily_video() -> dict[str, Any]:
    """Did the daily producer RUN, and did it PRODUCE a creative today?"""
    beats = _heartbeats()
    hb = beats.get("daily_video") or {}
    ran = bool(hb.get("at"))
    detail: dict[str, Any] = {"heartbeat": hb.get("at"), "last_run": hb.get("at"), "last_attempt": hb.get("at")}
    enabled = _on("DAILY_VIDEO_ENABLED", "0")
    produced = False
    artifact_id = ""
    artifact_path = ""
    try:
        from app.marketing import daily_video

        st = daily_video.status()
        detail["clients"] = len(st.get("clients") or [])
        generated = [c for c in (st.get("clients") or []) if c.get("generated_today")]
        produced = bool(generated)
        artifact_id = ",".join(str(c.get("client_id")) for c in generated)[:160]
        detail["generated_today"] = len(generated)
        artifact_path = str(daily_video._STATE())
    except Exception as exc:
        detail["probe_error"] = str(exc)[:160]
    age = _age_s(_newest_mtime(artifact_path)) if artifact_path else None
    detail["artifact_path"] = artifact_path
    detail["last_artifact_id"] = artifact_id
    return _verdict("daily_video", enabled=enabled, ran=ran, produced=produced, age_s=age, detail=detail)


def probe_local_render() -> dict[str, Any]:
    """Did a local render job actually COMPLETE? (data plane owned by T02)

    Reads the render-plane job store defensively: when the plane is not built
    yet, or its flag is off, this reports honestly instead of guessing.
    """
    beats = _heartbeats()
    hb = beats.get("daily_video") or {}
    ran = bool(hb.get("at"))
    enabled = _on("CREATIVE_RENDER_PLANE_ENABLED", "0")
    detail: dict[str, Any] = {"heartbeat": hb.get("at"), "last_run": hb.get("at")}
    produced = False
    artifact_id = ""
    artifact_hash = ""
    artifact_path = ""
    plane_available = False
    try:
        from app.render_plane import jobstore  # type: ignore

        plane_available = True
        # SYNC reader (T02). The async list_jobs cannot be awaited in this
        # event-loop-free web context: the old loop called it synchronously,
        # got a coroutine, degraded into plane_error, and could NEVER report
        # `produced` — the ran-vs-produced fake-green. recent_done() is the seam.
        done = jobstore.recent_done()
        if isinstance(done, dict) and done.get("ok"):
            items = list(done.get("items") or [])
            completed = int(done.get("count") or len(items))
            detail["completed_jobs"] = completed
            if items:
                latest = items[0]  # newest finished first
                artifact_id = str(latest.get("job_id") or "")
                artifact_hash = str(latest.get("artifact_sha256") or "")
                artifact_path = str(latest.get("artifact_path") or "")
            # A done ROW is not a produced ARTIFACT: the file must exist on disk.
            # Counting rows alone graded a missing file as fresh (age=None) and so
            # as `ok` — the very fake-green this probe exists to catch.
            if artifact_path and os.path.isfile(artifact_path):
                produced = True
            elif completed > 0:
                produced = False
                detail["artifact_missing"] = True
                detail["missing_artifact_path"] = artifact_path
        else:
            # Genuinely unreadable store -> honest plane_error, never a fake zero.
            detail["plane_error"] = str((done or {}).get("error") or "plane_unreadable")[:120]
    except Exception as exc:
        detail["plane_error"] = str(exc)[:120]
    if not plane_available and enabled:
        detail["plane_available"] = False
    age = _age_s(_newest_mtime(artifact_path)) if artifact_path else None
    # An unmeasurable age is NOT evidence of freshness: never let an artifact we
    # cannot date (e.g. the file vanished between isfile() and stat) grade as ok.
    if produced and age is None:
        produced = False
        detail["artifact_unmeasurable"] = True
    detail.update(
        {
            "plane_available": plane_available,
            "artifact_path": artifact_path,
            "last_artifact_id": artifact_id,
            "last_artifact_hash": artifact_hash,
        }
    )
    reason_override = None
    if detail.get("artifact_missing"):
        reason_override = "artifact_missing: newest done row has no file on disk"
    elif detail.get("artifact_unmeasurable"):
        reason_override = "artifact_unmeasurable: file exists but cannot be dated"
    return _verdict(
        "local_render",
        enabled=enabled,
        ran=ran,
        produced=produced,
        age_s=age,
        detail=detail,
        reason_override=reason_override,
    )


def probe_novelty_gate() -> dict[str, Any]:
    """Did the novelty gate RUN and ACCEPT a lineage entry (produce evidence)?"""
    beats = _heartbeats()
    hb = beats.get("daily_video") or {}
    ran = bool(hb.get("at"))
    enabled = _on("CREATIVE_NOVELTY_ENABLED", "1")
    detail: dict[str, Any] = {"heartbeat": hb.get("at"), "last_run": hb.get("at")}
    produced = False
    artifact_path = ""
    count = 0
    try:
        from app.marketing.creative_os import novelty

        artifact_path = novelty._novelty_dir()
        if os.path.isdir(artifact_path):
            for name in os.listdir(artifact_path):
                if name.endswith(".jsonl"):
                    count += 1
        produced = count > 0
    except Exception as exc:
        detail["probe_error"] = str(exc)[:160]
    age = _age_s(_newest_mtime(artifact_path)) if artifact_path else None
    detail.update({"artifact_path": artifact_path, "tenant_lineages": count, "last_artifact_id": f"lineages:{count}"})
    return _verdict("novelty_gate", enabled=enabled, ran=ran, produced=produced, age_s=age, detail=detail)


def probe_tg_delivery() -> dict[str, Any]:
    """Did Telegram delivery PRODUCE a receipt? (Q10)"""
    beats = _heartbeats()
    hb = beats.get("video_delivery") or {}
    ran = bool(hb.get("at"))
    enabled = _on("VIDEO_TELEGRAM_DELIVERY_ENABLED", "0")
    detail: dict[str, Any] = {"heartbeat": hb.get("at"), "last_run": hb.get("at")}
    produced = False
    delivered = 0
    last_mid = ""
    newest = None
    ledger_dir = ""
    try:
        from app.marketing import delivery_ledger

        ledger_dir = delivery_ledger._LEDGER_DIR()
        if os.path.isdir(ledger_dir):
            for name in os.listdir(ledger_dir):
                if not name.endswith(".jsonl"):
                    continue
                fp = os.path.join(ledger_dir, name)
                try:
                    with open(fp, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            if isinstance(rec, dict) and rec.get("event") == "video_delivered":
                                delivered += 1
                                last_mid = str((rec.get("meta") or {}).get("message_id") or last_mid)
                                m = _newest_mtime(fp)
                                if m is not None and (newest is None or m > newest):
                                    newest = m
                except Exception:
                    continue
        produced = delivered > 0
    except Exception as exc:
        detail["probe_error"] = str(exc)[:160]
    age = _age_s(newest)
    detail.update(
        {
            "artifact_path": ledger_dir,
            "deliveries": delivered,
            "last_artifact_id": last_mid,
        }
    )
    return _verdict("tg_delivery", enabled=enabled, ran=ran, produced=produced, age_s=age, detail=detail)


_PROBES: dict[str, Callable[[], dict[str, Any]]] = {
    "daily_video": probe_daily_video,
    "local_render": probe_local_render,
    "novelty_gate": probe_novelty_gate,
    "tg_delivery": probe_tg_delivery,
}


def probe_automation(name: str) -> dict[str, Any]:
    """Run one named probe. Unknown name ⇒ honest ``unknown``. Never raises."""
    key = str(name or "").strip()
    fn = _PROBES.get(key)
    if fn is None:
        return {
            "automation": key,
            "enabled": False,
            "ran": None,
            "produced": False,
            "stale": None,
            "artifact_age_s": None,
            "verified": False,
            "status": "unknown",
            "reason": f"unknown automation '{key}'",
            "owner_feed": {},
        }
    try:
        return fn()
    except Exception as exc:
        return {
            "automation": key,
            "enabled": False,
            "ran": None,
            "produced": False,
            "stale": None,
            "artifact_age_s": None,
            "verified": False,
            "status": "unknown",
            "reason": f"probe_error:{str(exc)[:120]}",
            "owner_feed": {},
        }


def health() -> dict[str, Any]:
    """End-to-end health for every video automation. Never raises.

    ``ok`` is True only when every automation is ``ok`` or ``gated_inert`` — a
    ``warn`` (ran-but-produced-nothing, or stale) is NOT healthy.
    """
    rows = [probe_automation(name) for name in _PROBES]
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    degraded = [r["automation"] for r in rows if r["status"] in ("warn", "down", "unknown")]
    return {
        "ok": not degraded,
        "automations": rows,
        "by_status": by_status,
        "degraded": degraded,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def local_render_status() -> dict[str, Any]:
    """Compact local-render status for the daily-video operator view."""
    p = probe_automation("local_render")
    return {
        "enabled": p.get("enabled"),
        "status": p.get("status"),
        "produced": p.get("produced"),
        "plane_available": p.get("plane_available"),
        "reason": p.get("reason"),
        "last_artifact_id": p.get("last_artifact_id"),
    }


__all__ = [
    "STALE_AFTER_S",
    "health",
    "local_render_status",
    "probe_automation",
    "probe_daily_video",
    "probe_local_render",
    "probe_novelty_gate",
    "probe_tg_delivery",
]
