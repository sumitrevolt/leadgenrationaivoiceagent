"""
Hermes 🛰️ — Infrastructure Handler agent (AI staff).
=====================================================

Ek dedicated infra-ops brain jo poore stack ki sehat ka EK snapshot deta hai:
app readiness (db+redis), disk/memory, scheduled-job dead-man, queue backlog,
LLM-chain fail-rate, backup freshness — 0-100 INFRA SCORE + Hinglish actions.

Kavya (ops_watchdog = service/process checks) aur Tara (telephony readiness) ke
UPAR ek aggregator/diagnoser — unke engines REUSE karta hai, replace nahi.

Wiring:
  - hourly `watchdog` job (team_scheduler) -> `run_watch()` — GATED `INFRA_HANDLER=1`
    (default OFF = sirf manual API). Alert email NOTIFY_EMAIL pe (6h dedupe).
  - team_pulse rotation me "hermes" monitor (cheap, flag-independent).
  - API: GET /api/growth/infra/hermes (admin) — live snapshot.

Store: data/infra_scans.jsonl (auto-trim). Kabhi raise nahi karta (har check
defensive — jo cheez padh nahi sakta usse "unknown" bolta hai, crash nahi).
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = Path("data") / "infra_scans.jsonl"
_MAX_ROWS = 500
ALERT_SCORE = 70  # isse neeche => (gated) email alert
ALERT_DEDUPE_HOURS = 6  # baar-baar same alert mat bhejo
DISK_WARN, DISK_CRIT = 85, 92  # % used
MEM_WARN = 90  # % used
BACKUP_STALE_HOURS = 48


def _enabled() -> bool:
    return (os.getenv("INFRA_HANDLER") or "").strip().lower() in ("1", "true", "yes", "on")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Individual checks — har ek defensive, "unknown" > crash
# --------------------------------------------------------------------------- #
def _check_disk() -> dict[str, Any]:
    try:
        u = shutil.disk_usage(".")
        pct = round(u.used / u.total * 100, 1)
        return {"ok": pct < DISK_WARN, "pct_used": pct, "free_gb": round(u.free / 1e9, 1)}
    except Exception:
        return {"ok": None, "pct_used": None}


def _check_memory() -> dict[str, Any]:
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0].rstrip(":") in ("MemTotal", "MemAvailable"):
                    info[parts[0].rstrip(":")] = int(parts[1])
        total, avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
        if not total:
            return {"ok": None}
        pct = round((total - avail) / total * 100, 1)
        return {"ok": pct < MEM_WARN, "pct_used": pct, "available_mb": avail // 1024}
    except Exception:  # Windows/dev — /proc nahi
        return {"ok": None}


async def _check_ready() -> dict[str, Any]:
    """App ki /health/ready (db+redis truth). Worker container se app host pe."""
    # PORT TRAP: the app listens on 8080 INSIDE the container/network and is only
    # published to 8000 on the HOST. From a worker container `app:8000` is a silent
    # ECONNREFUSED (verified live: app:8000 -> 000, app:8080 -> 200), so every URL
    # here used to fail and this check could never report ready. In-network = 8080.
    urls = [
        (os.getenv("SELF_HEALTH_URL") or "").strip(),
        "http://app:8080/health/ready",
        "http://app:8000/health/ready",  # legacy/host-published fallback
        "http://127.0.0.1:8080/health/ready",
    ]
    try:
        import httpx

        for url in [u for u in urls if u]:
            try:
                async with httpx.AsyncClient(timeout=4) as c:
                    r = await c.get(url)
                if r.status_code == 200:
                    d = (
                        r.json()
                        if r.headers.get("content-type", "").startswith("application/json")
                        else {}
                    )
                    checks = d.get("checks") or {}
                    return {
                        "ok": (d.get("status") == "healthy"),
                        "db": (checks.get("database") or {}).get("status"),
                        "redis": (checks.get("redis") or {}).get("status"),
                        "url": url,
                    }
                return {"ok": False, "http": r.status_code, "url": url}
            except Exception:
                continue
    except Exception:
        pass
    return {"ok": None, "note": "ready endpoint unreachable (dev/test?)"}


def _check_jobs() -> dict[str, Any]:
    try:
        from app.platform import automation_health

        h = automation_health.health()
        return {
            "ok": h.get("status") == "healthy",
            "status": h.get("status"),
            "overdue": h.get("overdue") or [],
            "queue": h.get("queue") or {},
            "queue_backlogged": bool(h.get("queue_backlogged")),
        }
    except Exception:
        return {"ok": None}


def _check_llm() -> dict[str, Any]:
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(window=200) or {}
        rate = float(st.get("fallback_or_fail_rate") or 0)
        return {
            "ok": rate < 0.5,
            "fallback_or_fail_rate": rate,
            "providers": len(st.get("providers") or {}),
        }
    except Exception:
        return {"ok": None}


def _check_embedder() -> dict[str, Any]:
    """
    Voice-KB embedder assets present? (2026-06-12 prod-down lesson: model cache
    missing => fastembed runtime HF download => event-loop hang.) Sirf DISK
    check — model load NahI karte (heavy). FASTEMBED_CACHE_PATH ya /tmp cache
    me onnx model file dikhni chahiye.
    """
    try:
        import os as _os

        dirs = [
            _os.getenv("FASTEMBED_CACHE_PATH") or "",
            "/opt/fastembed_cache",
            "/tmp/fastembed_cache",
        ]
        for d in dirs:
            if d and Path(d).is_dir():
                onnx = list(Path(d).rglob("*.onnx"))
                if onnx:
                    return {"ok": True, "cache_dir": d, "models": len(onnx)}
        return {
            "ok": False,
            "note": "fastembed model cache MISSING — image bake/redeploy karo (runtime HF download = freeze risk)",
        }
    except Exception:
        return {"ok": None}


def _check_backups() -> dict[str, Any]:
    """Newest file in backups/ ki age (container me dir na ho => unknown)."""
    try:
        candidates: list[Path] = []
        for d in (Path("backups"), Path("backups") / "data", Path("/opt/leadgen/backups")):
            if d.is_dir():
                candidates += [p for p in d.iterdir() if p.is_file()]
        if not candidates:
            return {"ok": None, "note": "backups dir not visible here"}
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        age_h = round((_now().timestamp() - newest.stat().st_mtime) / 3600, 1)
        return {"ok": age_h <= BACKUP_STALE_HOURS, "newest": newest.name, "age_hours": age_h}
    except Exception:
        return {"ok": None}


# --------------------------------------------------------------------------- #
# Snapshot + score
# --------------------------------------------------------------------------- #
async def snapshot() -> dict[str, Any]:
    """Poora infra snapshot + 0-100 score + Hinglish actions. Kabhi raise nahi."""
    checks = {
        "ready": await _check_ready(),
        "disk": _check_disk(),
        "memory": _check_memory(),
        "jobs": _check_jobs(),
        "llm": _check_llm(),
        "backups": _check_backups(),
        "embedder": _check_embedder(),
    }
    score = 100
    actions: list[str] = []

    r = checks["ready"]
    if r.get("ok") is False:
        score -= 40
        actions.append(
            "App /health/ready unhealthy — `docker ps` + `docker logs leadgen_app` dekho, db/redis container check karo."
        )

    d = checks["disk"]
    if isinstance(d.get("pct_used"), (int, float)):
        if d["pct_used"] >= DISK_CRIT:
            score -= 35
            actions.append(
                f"DISK CRITICAL {d['pct_used']}% — purane backups/media-cache साफ karo (`du -sh /opt/leadgen/*`)."
            )
        elif d["pct_used"] >= DISK_WARN:
            score -= 20
            actions.append(
                f"Disk {d['pct_used']}% — jaldi cleanup plan karo (backups rotate, docker image prune)."
            )

    m = checks["memory"]
    if m.get("ok") is False:
        score -= 10
        actions.append(f"Memory {m.get('pct_used')}% — heavy job/leak check (`docker stats`).")

    j = checks["jobs"]
    if j.get("overdue"):
        score -= min(30, 10 * len(j["overdue"]))
        actions.append(
            "Overdue jobs: "
            + ", ".join(j["overdue"][:5])
            + " — worker/scheduler containers check karo."
        )
    if j.get("queue_backlogged"):
        score -= 15
        actions.append(
            f"Celery backlog {j.get('queue', {}).get('celery')} — worker slow/dead (`docker logs leadgen_worker`)."
        )

    llm = checks["llm"]
    if llm.get("ok") is False:
        score -= 10
        actions.append(
            f"LLM fail/fallback rate {llm.get('fallback_or_fail_rate')} — provider keys/quota dekho (/api/growth/infra/llm)."
        )

    b = checks["backups"]
    if b.get("ok") is False:
        score -= 10
        actions.append(
            f"Backup {b.get('age_hours')}h purana — pg_backup cron + offsite mail check karo."
        )

    e = checks["embedder"]
    if e.get("ok") is False:
        score -= 10
        actions.append(
            "Voice-KB embedding model cache missing — image rebuild/bake karo (runtime download = freeze risk)."
        )

    score = max(0, score)

    # --- Skill-grounded recommendations (Fable skills -> Hermes) --- #
    # Har detected issue ke liye skill_pack se sabse relevant PROJECT skill suggest
    # karo, taaki Hermes ka action sirf "kya" nahi "kaise" bhi bataye (skill snippet
    # padh ke). skill_pack off / koi match nahi = chup-chap skip (never-raise).
    skills_suggested: list[dict[str, str]] = []
    try:
        from app.platform import skill_pack

        if skill_pack.enabled():
            _topic = {
                "ready": "production down health deploy incident",
                "disk": "infra disk cleanup backups hardening",
                "memory": "infra memory leak performance",
                "jobs": "scheduler jobs automation loop dead-man",
                "llm": "llm provider quota fallback circuit-breaker",
                "backups": "backup restore offsite postgres",
                "embedder": "model bake embedder voice asset",
            }
            _seen: set[str] = set()
            for _k, _ok_is_false in (
                ("ready", checks["ready"].get("ok") is False),
                (
                    "disk",
                    isinstance(checks["disk"].get("pct_used"), (int, float))
                    and checks["disk"]["pct_used"] >= DISK_WARN,
                ),
                ("memory", checks["memory"].get("ok") is False),
                (
                    "jobs",
                    bool(checks["jobs"].get("overdue") or checks["jobs"].get("queue_backlogged")),
                ),
                ("llm", checks["llm"].get("ok") is False),
                ("backups", checks["backups"].get("ok") is False),
                ("embedder", checks["embedder"].get("ok") is False),
            ):
                if not _ok_is_false:
                    continue
                for s in skill_pack.find(_topic[_k], k=1):
                    nm = s.get("name")
                    if nm and nm not in _seen:
                        _seen.add(nm)
                        skills_suggested.append(
                            {"issue": _k, "skill": nm, "why": (s.get("description") or "")[:120]}
                        )
            # Healthy bhi ho to bhi "fable operating manual" hamesha point-of-reference
            if not skills_suggested:
                for s in skill_pack.find("fable operating manual project discipline", k=1):
                    if s.get("name"):
                        skills_suggested.append(
                            {
                                "issue": "general",
                                "skill": s["name"],
                                "why": (s.get("description") or "")[:120],
                            }
                        )
    except Exception:
        pass
    if skills_suggested:
        actions.append(
            "📚 Relevant skills (padho phir act): "
            + ", ".join(sorted({x["skill"] for x in skills_suggested}))
        )

    return {
        "agent": "hermes",
        "score": score,
        "status": (
            "healthy" if score >= 85 else ("attention" if score >= ALERT_SCORE else "critical")
        ),
        "checks": checks,
        "actions": actions or ["Sab theek — koi action nahi chahiye."],
        "skills": skills_suggested,
        "at": _now().isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------- #
# Persistence + watchdog hook
# --------------------------------------------------------------------------- #
def _append_scan(row: dict[str, Any]) -> None:
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if _STORE.exists():
            lines = _STORE.read_text(encoding="utf-8").splitlines()[-(_MAX_ROWS - 1) :]
        lines.append(json.dumps(row, ensure_ascii=False))
        _STORE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def _last_alert_at() -> datetime | None:
    try:
        if not _STORE.exists():
            return None
        for line in reversed(_STORE.read_text(encoding="utf-8").splitlines()):
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("alerted"):
                return datetime.fromisoformat(rec["at"])
    except Exception:
        pass
    return None


def recent_scans(limit: int = 20) -> list[dict[str, Any]]:
    try:
        if not _STORE.exists():
            return []
        out = []
        for line in _STORE.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return list(reversed(out))
    except Exception:
        return []


async def run_watch() -> dict[str, Any]:
    """Hourly watchdog hook — GATED INFRA_HANDLER=1 (off => inert). Kabhi raise nahi."""
    if not _enabled():
        return {"ok": True, "skipped": "INFRA_HANDLER off"}
    try:
        snap = await snapshot()
        alerted = False
        if snap["score"] < ALERT_SCORE:
            last = _last_alert_at()
            if last is None or (_now() - last) > timedelta(hours=ALERT_DEDUPE_HOURS):
                notify = os.environ.get("NOTIFY_EMAIL", "").strip()
                if notify:
                    try:
                        from app.integrations.email_sender import email_sender

                        await email_sender.send_email(
                            [notify],
                            f"🛰️ Hermes INFRA alert: score {snap['score']}/100 ({snap['status']})",
                            "Infra issues:\n\n- "
                            + "\n- ".join(snap["actions"])
                            + "\n\n(Hermes infra_handler hourly scan)",
                        )
                        alerted = True
                    except Exception as e:
                        logger.warning(f"[hermes] alert email failed: {e}")
        _append_scan(
            {
                "at": snap["at"],
                "score": snap["score"],
                "status": snap["status"],
                "alerted": alerted,
                "actions": snap["actions"][:5],
            }
        )
        try:
            from app.platform import team

            team.log_event(
                "hermes",
                "infra_scan",
                f"infra {snap['score']}/100 ({snap['status']})"
                + (" · ALERT sent" if alerted else ""),
                status="ok" if snap["score"] >= ALERT_SCORE else "error",
            )
        except Exception:
            pass
        return {"ok": True, "score": snap["score"], "alerted": alerted}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[hermes] run_watch failed: {e}")
        return {"ok": False, "error": str(e)}
