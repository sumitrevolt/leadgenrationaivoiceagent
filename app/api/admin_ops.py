"""
Admin Ops API
=============
POST /api/admin/campaign/launch  → outbound call campaign (durable Celery task,
                                    app.tasks.calling.run_campaign_task; falls back
                                    to asyncio-subprocess fire_calls.py if broker down)
GET  /api/admin/campaign/status  → last run status (Redis)
GET  /api/admin/system/summary   → activation readiness + system snapshot

Auth: require_admin (Bearer JWT from /app/admin-login).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import log_audit
from app.api.auth_deps import require_admin
from app.models.base import get_async_db
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin Ops"])


def _call_transcripts_root() -> str:
    """Call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return str(call_transcripts_dir())


_BASE = (
    "/app"
    if os.path.isdir("/app")
    else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)
_CAMPAIGN_KEY = "admin:campaign:last_run"

# Running campaign subprocess (web process holds child ref for Stop).
_CAMPAIGN_PROC: dict[str, object] = {}

# ── Redis (optional; graceful skip) ─────────────────────────────────────────
_r: object | None = None


def _redis() -> object | None:
    global _r
    if _r is not None:
        return _r
    try:
        import redis as _redis_lib

        url = (os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()
        client = _redis_lib.Redis.from_url(url, socket_connect_timeout=2, decode_responses=True)
        client.ping()
        _r = client
        return _r
    except Exception:
        return None


def _redis_set(key: str, data: dict, ex: int = 86400) -> None:
    try:
        r = _redis()
        if r:
            r.setex(key, ex, json.dumps(data))  # type: ignore[union-attr]
    except Exception:
        pass


def _redis_get(key: str) -> dict:
    try:
        r = _redis()
        if r:
            raw = r.get(key)  # type: ignore[union-attr]
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return {}


# ── Models ───────────────────────────────────────────────────────────────────
class CampaignLaunchReq(BaseModel):
    limit: int = 10
    dry_run: bool = False
    niche: str | None = None
    client_id: str | None = None
    platform: bool = False


class UpiConfigureReq(BaseModel):
    vpa: str


class UpiActivateReq(BaseModel):
    client_id: str
    plan: str = "starter"
    clear_trial: bool = True
    # Optional legacy invoice/subscription owner id to bind onto the marketing
    # client (ADR-095 dual-identity). Idempotent; refuses cross-tenant steal.
    billing_client_id: str = ""


class VoiceGeminiKeysReq(BaseModel):
    keys: list[str] = []
    voice_primary: bool = True


class TrustTurnstileReq(BaseModel):
    site_key: str
    secret_key: str


class TrustSentryReq(BaseModel):
    dsn: str


class TrustPosthogReq(BaseModel):
    api_key: str
    host: str | None = None


def _upi_info() -> dict:
    """UPI VPA + WA screenshot verify link (no Razorpay)."""
    try:
        from app.platform import upi_config

        return upi_config.info()
    except Exception:
        vpa = (os.environ.get("UPI_VPA") or "").strip()
        wa = (os.environ.get("UPI_VERIFY_WA") or "918459012607").strip().lstrip("+")
        wa_link = f"https://wa.me/{wa}?text=" + __import__("urllib.parse").quote(
            "Payment screenshot — plan activate karo please"
        )
        return {"enabled": bool(vpa), "vpa": vpa, "wa_phone": wa, "wa_link": wa_link}


def _pending_upi_queue(limit: int = 20) -> list[dict]:
    """Real pending UPI submissions only — not every trial/free client.

    ADR-114: listing all trial clients as 'payment pending' was fake revenue
    urgency. Authoritative source = upi_payments.list_payments('pending');
    client metadata is a join only.
    """
    try:
        from app.platform import upi_payments

        rows = upi_payments.list_payments("pending") or []
        pending: list[dict] = []
        client_by_id: dict = {}
        try:
            from app.marketing import clients_store

            for c in clients_store.list_clients() or []:
                cid = str(c.get("id") or "")
                if cid:
                    client_by_id[cid] = c
        except Exception:
            client_by_id = {}
        for p in rows:
            if len(pending) >= limit:
                break
            cid = str(p.get("client_id") or "")
            c = client_by_id.get(cid) or {}
            pending.append(
                {
                    "client_id": cid or None,
                    "payment_id": p.get("id"),
                    "business_name": c.get("business_name") or p.get("business_name"),
                    "phone": c.get("phone") or p.get("phone"),
                    "plan": p.get("plan") or c.get("plan") or "trial",
                    "niche": c.get("niche"),
                    "amount": p.get("amount"),
                    "upi_ref": p.get("upi_ref"),
                    "created": p.get("created_at") or p.get("submitted_at") or c.get("created_at"),
                }
            )
        return pending
    except Exception:
        return []


def _trust_summary() -> dict:
    try:
        from app.platform import posthog_config, trust_config

        return {**trust_config.status(), "posthog": posthog_config.status()}
    except Exception:
        return {}


# ── Pre-flight: leads ready to call ─────────────────────────────────────────
def _leads_ready() -> dict:
    """Uncontacted-with-phone leads — EXACTLY what fire_calls.py would dial.

    Same WHERE clause as scripts/fire_calls.get_prospects so the count matches
    what a campaign will actually call. Defensive: any failure → available=False.
    """
    try:
        import urllib.parse as up

        import psycopg2

        dburl = os.environ.get("DATABASE_URL", "")
        if not dburl.startswith("postgres"):
            return {"available": False, "reason": "no_postgres_dsn"}
        p = up.urlparse(dburl)
        conn = psycopg2.connect(
            host=p.hostname,
            port=p.port or 5432,
            dbname=p.path.lstrip("/"),
            user=p.username,
            password=p.password,
            connect_timeout=4,
        )
        cur = conn.cursor()
        cur.execute(
            """SELECT COALESCE(NULLIF(LOWER(niche),''),'general') AS n, COUNT(*)
            FROM leads
            WHERE phone IS NOT NULL AND phone <> ''
              AND COALESCE(call_attempts,0) = 0
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15"""
        )
        rows = cur.fetchall()
        conn.close()
        by_niche = [{"niche": r[0], "count": int(r[1])} for r in rows]
        total = sum(r["count"] for r in by_niche)
        return {"available": True, "total": total, "by_niche": by_niche}
    except Exception as exc:
        return {"available": False, "reason": str(exc)[:120]}


def _call_stats() -> dict:
    """Recent call outcomes / qualified summary (pure-python, never raises)."""
    try:
        from app.platform import call_insights

        return call_insights.quick_stats()
    except Exception as exc:
        return {"error": str(exc)[:120]}


@router.get("/leads/ready", summary="Uncontacted leads ready to call (campaign pre-flight)")
async def leads_ready(_user=Depends(require_admin)):
    return await asyncio.to_thread(_leads_ready)


@router.get("/calls/recent", summary="Recent call outcomes / qualified summary")
async def calls_recent(_user=Depends(require_admin)):
    return await asyncio.to_thread(_call_stats)


def _load_call_transcript(call_id: str) -> dict | None:
    """Find one stream call transcript by stream_sid / call_id (JSONL tail scan)."""
    cid = (call_id or "").strip()
    if not cid:
        return None
    import json
    import os

    root = _call_transcripts_root()
    if not os.path.isdir(root):
        return None
    files = sorted(f for f in os.listdir(root) if f.endswith(".jsonl"))
    for name in reversed(files[-21:]):
        path = os.path.join(root, name)
        try:
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        rec = json.loads(ln)
                    except Exception:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    if (
                        str(rec.get("stream_sid") or "") == cid
                        or str(rec.get("call_sid") or "") == cid
                    ):
                        return rec
        except Exception:
            continue
    return None


@router.get("/calls/{call_id}/detail", summary="Call transcript + termination detail")
async def call_detail(call_id: str, _user=Depends(require_admin)):
    rec = await asyncio.to_thread(_load_call_transcript, call_id)
    if not rec:
        return {"ok": False, "call": None}
    return {
        "ok": True,
        "call": {
            "call_id": call_id,
            "stream_sid": rec.get("stream_sid"),
            "duration_s": rec.get("duration_s"),
            "user_turns": rec.get("user_turns"),
            "agent_turns": rec.get("agent_turns"),
            "completed_exchanges": rec.get("completed_exchanges"),
            "termination_reason": rec.get("termination_reason"),
            "termination_source": rec.get("termination_source"),
            "niche": rec.get("niche"),
            "client_name": rec.get("client_name"),
            "messages": rec.get("messages") or [],
            "turn_metrics": rec.get("turn_metrics"),
        },
    }


# ── Campaign endpoints ────────────────────────────────────────────────────────
@router.post("/campaign/launch", summary="Launch outbound call campaign")
async def launch_campaign(req: CampaignLaunchReq, _user=Depends(require_admin)):
    """
    Prefers a durable Celery task (app.tasks.calling.run_campaign_task) — survives
    web-process restarts and doesn't hold one of the 2 web workers for the full
    campaign duration (the old asyncio-subprocess path could hold one for up to
    320s per launch). Falls back to the asyncio-subprocess path only if the Celery
    broker is unreachable. Same compliance gates either way — single source of
    truth in app/telephony/campaign_compliance.py, shared with scripts/fire_calls.py.
    Single-flight: a Redis lock refuses a second launch while one is already running
    (idempotency — prevents double-dialing the same lead batch from concurrent
    admin clicks). Returns immediately; poll /api/admin/campaign/status for result.
    """
    if not 1 <= req.limit <= 200:
        raise HTTPException(status_code=400, detail="limit must be 1–200")

    from app.tasks.calling import acquire_campaign_lock, campaign_lock_held, release_campaign_lock

    if campaign_lock_held():
        raise HTTPException(
            status_code=409,
            detail="Campaign already running — check /api/admin/campaign/status",
        )
    # TTL scaled to worst-case runtime (~6s/call incl. the dial loop's
    # asyncio.sleep(4) pace-limiter) + buffer — a fixed 400s lock expires
    # mid-run for limit>~55, letting a second launch start concurrently and
    # re-dial leads the first run hasn't reached yet.
    if not acquire_campaign_lock(ttl_s=max(400, req.limit * 8 + 120)):
        raise HTTPException(status_code=409, detail="Campaign already running")

    # ── Session lifecycle (2026-08-02): operator Fire = canonical
    # create_voice_session → fresh VOICE_CALLS_PER_SESSION counter. Isi single
    # explicit lifecycle se session count reset hota hai — worker/scheduler
    # restart kabhi nahi. Daily cap (VOICE_DAILY_CALL_CAP) session-cycling ka
    # aggregate backstop rehta hai. Dry-run se koi session/reset nahi.
    session_id = None
    if not req.dry_run:
        try:
            from app.telephony import voice_launch as _vl_session

            session_id = await _vl_session.create_voice_session(
                owner=getattr(_user, "email", "admin") or "admin",
                niche=req.niche or "",
                label=f"launch:limit={req.limit}",
            )
        except Exception as _se:
            logger.warning(f"[voice_launch] session create on launch failed: {_se}")
            session_id = None

    try:
        from app.worker import celery_app

        async_result = celery_app.send_task(
            "app.tasks.calling.run_campaign_task",
            kwargs={
                "limit": req.limit,
                "dry_run": req.dry_run,
                "niche": req.niche or "",
                "client_id": req.client_id or "",
                "platform": req.platform,
                "transactional": False,
            },
        )
        # Lock release is the Celery task's own responsibility (its `finally`) once
        # it actually runs — NOT released here, so a second launch is refused for
        # the duration of this campaign even before the worker picks the task up.
        return {
            "queued": True,
            "limit": req.limit,
            "dry_run": req.dry_run,
            "platform": req.platform,
            "session_id": session_id,
            "via": "celery",
            "task_id": async_result.id,
            "poll": "/api/admin/campaign/status",
        }
    except Exception as exc:
        logger.warning(f"Celery campaign enqueue failed, falling back to subprocess: {exc}")
        # Lock stays held — the subprocess path below releases it (its own finally).

    # ---- Fallback: web-process subprocess (unchanged behaviour, only reached
    # when the Celery broker itself is unreachable) ----
    script = os.path.join(_BASE, "scripts", "fire_calls.py")
    if not os.path.isfile(script):
        release_campaign_lock()
        raise HTTPException(status_code=500, detail="fire_calls.py not found in container")

    cmd = [sys.executable, script, "--limit", str(req.limit)]
    if req.dry_run:
        cmd.append("--dry-run")
    if req.niche:
        cmd.extend(["--niche", req.niche])
    if req.client_id:
        cmd.extend(["--client-id", req.client_id])
    if req.platform:
        cmd.append("--platform")

    _redis_set(
        _CAMPAIGN_KEY,
        {
            "status": "running",
            "limit": req.limit,
            "dry_run": req.dry_run,
            "niche": req.niche,
            "platform": req.platform,
            "started_at": time.time(),
            "via": "subprocess_fallback",
            "output": "",
        },
    )

    async def _run_bg():
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=_BASE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            _CAMPAIGN_PROC["proc"] = proc
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=320)
            output = (stdout or b"").decode("utf-8", errors="replace")
            _redis_set(
                _CAMPAIGN_KEY,
                {
                    "status": "done",
                    "exit_code": proc.returncode,
                    "limit": req.limit,
                    "dry_run": req.dry_run,
                    "niche": req.niche,
                    "started_at": time.time(),
                    "finished_at": time.time(),
                    "via": "subprocess_fallback",
                    "output": output[-4000:],
                },
            )
        except asyncio.TimeoutError:
            _redis_set(
                _CAMPAIGN_KEY,
                {
                    "status": "timeout",
                    "limit": req.limit,
                    "dry_run": req.dry_run,
                    "finished_at": time.time(),
                    "via": "subprocess_fallback",
                    "output": "Timed out after 320s",
                },
            )
        except Exception as exc:
            _redis_set(
                _CAMPAIGN_KEY,
                {
                    "status": "error",
                    "error": str(exc),
                    "limit": req.limit,
                    "dry_run": req.dry_run,
                    "via": "subprocess_fallback",
                },
            )
        finally:
            release_campaign_lock()

    asyncio.create_task(_run_bg())

    return {
        "queued": True,
        "limit": req.limit,
        "dry_run": req.dry_run,
        "platform": req.platform,
        "via": "subprocess_fallback",
        "poll": "/api/admin/campaign/status",
    }


@router.get("/campaign/status", summary="Last campaign run status")
async def campaign_status(_user=Depends(require_admin)):
    """Poll this after launch. status: running | done | error | timeout | never_run"""
    st = _redis_get(_CAMPAIGN_KEY)
    return st if st else {"status": "never_run"}


@router.post("/campaign/stop", summary="Stop the currently running campaign")
async def campaign_stop(_user=Depends(require_admin)):
    """Stop the currently-running campaign — either path (stops placing NEW calls;
    an in-flight call already on the carrier completes, no new numbers dialed).

    Celery path: revokes the tracked task_id (best-effort — terminates the worker's
    current task run). Subprocess-fallback path: terminates the child process.
    """
    st = _redis_get(_CAMPAIGN_KEY) or {}
    stopped_any = False

    task_id = st.get("task_id")
    if task_id and st.get("via") == "celery" and st.get("status") == "running":
        try:
            from app.worker import celery_app

            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
            stopped_any = True
        except Exception as exc:
            logger.warning(f"campaign_stop celery revoke failed: {exc}")
        try:
            from app.tasks.calling import release_campaign_lock

            release_campaign_lock()
        except Exception:
            pass

    proc = _CAMPAIGN_PROC.get("proc")
    if proc is not None and getattr(proc, "returncode", 0) is None:
        try:
            proc.terminate()  # type: ignore[union-attr]
            stopped_any = True
        except ProcessLookupError:
            pass
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)[:200]) from exc

    if not stopped_any:
        return {"stopped": False, "reason": "no_running_campaign"}

    st.update({"status": "stopped", "finished_at": time.time()})
    _redis_set(_CAMPAIGN_KEY, st)
    return {"stopped": True}


# ── System summary ────────────────────────────────────────────────────────────
@router.get("/system/summary", summary="System snapshot for God Mode panel")
async def system_summary(_user=Depends(require_admin)):
    """Vobiz calling + UPI payment readiness — God Mode panel."""
    import datetime

    readiness: dict = {}
    try:
        from app.api.activation import get_activation_summary

        readiness = await get_activation_summary()
    except Exception as exc:
        readiness = {"error": str(exc)}

    ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    trai_start = int(os.environ.get("COMPLIANCE_PROMO_START", "10").split(":")[0])
    trai_end = int(os.environ.get("COMPLIANCE_PROMO_END", "19").split(":")[0])
    calling_open = trai_start <= ist_now.hour < trai_end

    last_campaign = _redis_get(_CAMPAIGN_KEY) or {"status": "never_run"}

    provider = (os.environ.get("TELEPHONY_PROVIDER") or "vobiz").strip().lower()
    try:
        from app.platform import platform_dial as _platform_dial

        platform_dial_enabled = bool(_platform_dial.enabled())
        platform_dial_limit = int(_platform_dial.dial_limit())
    except Exception:
        platform_dial_enabled = False
        platform_dial_limit = 0
    try:
        from app.telephony import voice_launch as _vl

        voice_launch_snapshot = await _vl.launch_status()
    except Exception as _vle:
        voice_launch_snapshot = {"error": str(_vle)}
    try:
        from app.platform import approval_notifier as _approval_notifier

        approval_notify_health = _approval_notifier.get_health()
    except Exception:
        approval_notify_health = {"enabled": False, "error": True}
    vobiz_ok = bool(os.environ.get("VOBIZ_AUTH_ID") and os.environ.get("VOBIZ_AUTH_TOKEN"))
    flags = {
        "TELEPHONY_PROVIDER": provider,
        "PROVIDER_CREDS": vobiz_ok,
        "VOBIZ_CREDS": vobiz_ok,
        "VOBIZ_CALLER_ID": bool(os.environ.get("VOBIZ_CALLER_ID", "").strip()),
        "VOBIZ_CALL_RECORD": bool(int(os.environ.get("VOBIZ_CALL_RECORD", "0"))),
        "AUTO_EMAIL_OUTREACH": os.environ.get("AUTO_EMAIL_OUTREACH", "").lower() in ("1", "true"),
        "REPLY_AGENT": os.environ.get("REPLY_AGENT", "").lower() in ("1", "true"),
        "GROQ_STT": bool(os.environ.get("GROQ_API_KEY", "").strip()),
        "UPI_VPA": bool(os.environ.get("UPI_VPA", "").strip()),
    }

    telephony = readiness.get("telephony") or {}
    upi = _upi_info()

    caller_id = os.environ.get("VOBIZ_CALLER_ID", "unset")

    # Pre-flight calling data (blocking DB → thread; never breaks the panel).
    try:
        leads_ready = await asyncio.wait_for(asyncio.to_thread(_leads_ready), timeout=6)
    except Exception:
        leads_ready = {"available": False, "reason": "timeout"}
    try:
        call_stats = await asyncio.wait_for(asyncio.to_thread(_call_stats), timeout=4)
    except Exception:
        call_stats = {}

    return {
        "readiness": readiness,
        "upi": upi,
        "pending_upi": _pending_upi_queue(15),
        "trust": _trust_summary(),
        "leads_ready": leads_ready,
        "call_stats": call_stats,
        "trai": {
            "calling_open": calling_open,
            "window": f"{trai_start:02d}:00–{trai_end:02d}:00 IST",
            "ist_hour": ist_now.hour,
        },
        "telephony_provider": provider,
        "platform_dial": {
            "enabled": platform_dial_enabled,
            "limit": platform_dial_limit,
            "hard_off": not platform_dial_enabled,
        },
        "voice_launch": voice_launch_snapshot,
        "approval_notify": approval_notify_health,
        "vobiz_caller_id": os.environ.get("VOBIZ_CALLER_ID", "unset"),
        # Razorpay removed 2026-06-18 — manual UPI only; stub for JS compat.
        "razorpay": {"key_set": False, "live_key": False, "key_prefix": "removed"},
        "telephony_score": telephony.get("score", 0),
        "telephony_missing": telephony.get("missing", []),
        "telephony_actions": telephony.get("actions", []),
        "ready_for_calling": readiness.get("ready_for_calling", False),
        "last_campaign": last_campaign,
        "flags": flags,
        "generated_at": ist_now.strftime("%H:%M IST"),
    }


@router.get("/upi/pending", summary="Clients waiting for UPI screenshot activation")
async def upi_pending(_user=Depends(require_admin)):
    return {"pending": _pending_upi_queue(30), "upi": _upi_info()}


# ── Controlled voice-calling launch (2026-07-17) ───────────────────────────────
@router.get("/voice-launch/status", summary="Controlled voice-calling launch status")
async def voice_launch_status(_user=Depends(require_admin)):
    """Kill switch, daily cap/remaining, training boundary, circuit-breaker,
    recording gate, campaign state + today's NUP/disposition tally."""
    from app.telephony import voice_launch as _vl

    return await _vl.launch_status()


class _VoiceKillReq(BaseModel):
    kill: bool


@router.post("/voice-launch/kill", summary="Engage/release the voice-calling kill switch")
async def voice_launch_kill(req: _VoiceKillReq, _user=Depends(require_admin)):
    """Global admin kill switch (data-file). kill=true => ALL outbound campaign calls
    become ineligible (fail-safe); env VOICE_LAUNCH_KILL, if set, overrides this."""
    from app.telephony import voice_launch as _vl

    ok = _vl.set_kill(bool(req.kill))
    logger.warning(
        f"[voice_launch] admin kill switch set kill={req.kill} by {getattr(_user, 'email', 'admin')}"
    )
    return {"ok": ok, "kill": bool(req.kill), "status": await _vl.launch_status()}


# ── Voice-launch SESSION endpoints (2026-08-02) ────────────────────────────────
class _SessionCreateReq(BaseModel):
    owner: str = "admin"
    niche: str = ""
    label: str = ""


@router.get("/voice-launch/session", summary="Current voice-launch session status")
async def voice_launch_session_status(_user=Depends(require_admin)):
    """Operator-visible used / cap / remaining / stopped + per-disposition counts
    for the current launch session (exactly VOICE_CALLS_PER_SESSION per session)."""
    from app.telephony import voice_launch as _vl

    return await _vl.session_status()


@router.post("/voice-launch/session", summary="Start a NEW voice-launch session (canonical reset)")
async def voice_launch_session_create(req: _SessionCreateReq, _user=Depends(require_admin)):
    """CANONICAL session lifecycle — naya session (attempt counter 0). Isi single
    explicit lifecycle se session count reset hota hai; worker/scheduler restart
    se KABHI nahi."""
    from app.telephony import voice_launch as _vl

    sid = await _vl.create_voice_session(owner=req.owner, niche=req.niche, label=req.label)
    if not sid:
        raise HTTPException(status_code=503, detail="Session create failed (Redis?)")
    logger.info(f"[voice_launch] new session {sid} by {getattr(_user, 'email', 'admin')}")
    return {"ok": True, "session_id": sid, "status": await _vl.session_status(sid)}


@router.post(
    "/voice-launch/session/stop", summary="Emergency-stop the current voice-launch session"
)
async def voice_launch_session_stop(_user=Depends(require_admin)):
    """Session-level emergency stop — naye provider calls block (jo call abhi
    in-flight hai wo complete hoti hai). used/remaining visible in status."""
    from app.telephony import voice_launch as _vl

    ok = await _vl.session_stop()
    logger.warning(f"[voice_launch] session STOP by {getattr(_user, 'email', 'admin')} ok={ok}")
    return {"ok": ok, "status": await _vl.session_status()}


@router.get(
    "/swara-enterprise/status",
    summary="Swara free-AI sticky routing + STT gate + training loop status",
)
async def swara_enterprise_status(_user=Depends(require_admin)):
    """Admin surface: route health, STT gate, training proposals — NO secrets."""
    out: dict = {"ok": True}
    try:
        from app.voice_agent.voice_sticky_route import health_snapshot, logical_routes

        out["router"] = health_snapshot()
        out["logical_routes"] = logical_routes()
    except Exception as e:
        out["router"] = {"error": type(e).__name__}
    try:
        from app.voice_agent.stt_understanding_gate import gate_snapshot

        out["stt_gate"] = gate_snapshot()
    except Exception as e:
        out["stt_gate"] = {"error": type(e).__name__}
    try:
        import json
        from pathlib import Path

        from app.voice_agent.postcall_qa import training_loop_enabled

        proposals = []
        p = Path("data") / "voice_training_proposals.jsonl"
        if p.exists():
            lines = p.read_text(encoding="utf-8").strip().splitlines()[-5:]
            for line in lines:
                try:
                    proposals.append(json.loads(line))
                except Exception:
                    continue
        out["training"] = {
            "loop_enabled": training_loop_enabled(),
            "recent_proposals": proposals,
        }
    except Exception as e:
        out["training"] = {"error": type(e).__name__}
    try:
        import os

        out["voice_env"] = {
            "VOICE_LLM_MODEL": (os.environ.get("VOICE_LLM_MODEL") or "")[:40],
            "VOICE_STICKY_ROUTE": os.environ.get("VOICE_STICKY_ROUTE", "1"),
            "VOICE_TOOLS": os.environ.get("VOICE_TOOLS", "0"),
            "STT_UNDERSTANDING_GATE": os.environ.get("STT_UNDERSTANDING_GATE", "1"),
            "PLATFORM_DIAL_DAILY": os.environ.get("PLATFORM_DIAL_DAILY", "0"),
            "VOICE_LAUNCH_CAMPAIGN": os.environ.get("VOICE_LAUNCH_CAMPAIGN", "0"),
            "OMNIROUTE_ENABLED": os.environ.get("OMNIROUTE_ENABLED", "0"),
        }
    except Exception:
        pass
    return out


def _admin_office() -> dict:
    """🏢 Admin Office — "Sumit ke kaam": 4 scattered pending-action queues (self-
    improve / content / code-patch / UPI approvals) ONE jagah, plain Hinglish +
    automation/revenue impact. Complements the existing 'Aaj ka business' overview
    (today_overview) — yeh sirf the manual-action gap bharta hai. Never raises."""
    tasks: list[dict] = []

    def _safe(fn) -> int:
        try:
            return int(fn() or 0)
        except Exception:
            return 0

    # 0) Hot Queue — GTM 0→1 bottleneck (owner 15-min sprint). Auto-send nahi.
    def _hq() -> int:
        from app.platform import reply_agent

        return len(reply_agent.hot_queue(limit=50, scope="boss") or [])

    n = _safe(_hq)
    if n > 0:
        tasks.append(
            {
                "id": "hot_queue",
                "icon": "🔥",
                "severity": "high",
                "count": n,
                "title": f"{n} Hot Queue replies aaj follow-up maangte hain",
                "why": "Interested/question replies — 15 min sprint: Call/WA draft, phir Done. Auto-send nahi.",
                "impact": "speed-to-lead = next paying Marketing customer",
                "cta_label": "Hot Queue kholo",
                "cta_target": "adminStartHere",
                "cta_href": "/app/inbox",
                "cta_action": "open_href",
            }
        )

    # 1) Self-improve approvals — agents waiting for the go-ahead
    def _si() -> int:
        from app.agents import self_improve

        return int(self_improve.approval_status().get("pending_count") or 0)

    n = _safe(_si)
    if n > 0:
        tasks.append(
            {
                "id": "selfimprove",
                "icon": "🤖",
                "severity": "medium",
                "count": n,
                "title": f"{n} self-improve task approve karo",
                "why": "Agents aapki OK ka wait kar rahe — tab tak loop ruka",
                "cta_label": "Approvals kholo",
                "cta_target": "sec-automation",
                "cta_action": "open_approvals",
            }
        )

    # 2) Content approvals — posts waiting for sign-off
    def _ca() -> tuple[int, dict[str, int]]:
        from app.marketing import content_approval

        rows = content_approval.pending("") or []
        by: dict[str, int] = {}
        for r in rows:
            cid = str((r or {}).get("client_id") or "unknown").strip() or "unknown"
            by[cid] = by.get(cid, 0) + 1
        return len(rows), by

    try:
        n, by_client = _ca()
    except Exception:
        n, by_client = 0, {}
    if n > 0:
        top_clients = sorted(by_client.items(), key=lambda kv: (-kv[1], kv[0]))[:4]

        def _client_label(cid: str) -> str:
            """Show business name when known — raw hex ids confuse non-tech admins."""
            key = str(cid or "").strip()
            if not key or key == "unknown":
                return "Unknown client"
            try:
                from app.marketing.clients_store import get_by_slug, get_client

                rec = get_client(key) or get_by_slug(key) or {}
                name = str(rec.get("business_name") or rec.get("company") or "").strip()
                if name:
                    return name
            except Exception:
                pass
            return key if len(key) <= 18 else (key[:10] + "…")

        client_hint = ", ".join(f"{_client_label(cid)} ({cnt})" for cid, cnt in top_clients) or "—"
        n_clients = len(by_client)
        tasks.append(
            {
                "id": "content",
                "icon": "✅",
                "severity": "high",
                "count": n,
                "clients_affected": n_clients,
                "title": f"{n} content posts · {n_clients} clients pe pending",
                "why": f"Pehle paid clients check karo (top: {client_hint}). Bulk approve yahan risky — Mission Control / Client Actions use karo.",
                "impact": "approve ke baad publish path open ho sakta hai",
                # Honest CTA: Mission Control is the real approvals surface (not scroll-only)
                "cta_label": "Mission Control",
                "cta_target": "sec-automation",
                "cta_href": "/app/automation",
                "cta_action": "open_href",
            }
        )

    # 3) Code-upgrader patches — Vikram's proposals need review
    def _cp() -> int:
        from app.agents import code_upgrader

        return len(code_upgrader.list_patches("proposed", 200) or [])

    n = _safe(_cp)
    if n > 0:
        tasks.append(
            {
                "id": "patches",
                "icon": "🩹",
                "severity": "medium",
                "count": n,
                "title": f"{n} code patch review karo",
                "why": "Vikram ne fixes propose kiye — core code kabhi auto-apply nahi hota",
                "cta_label": "Review kholo",
                "cta_target": "sec-automation",
                "cta_action": "open_approvals",
            }
        )

    # 4) UPI activations — customer paid, manual plan-activate pending (revenue!)
    try:
        upi_q = _pending_upi_queue(50) or []
    except Exception:
        upi_q = []
    if upi_q:
        n = len(upi_q)
        tasks.append(
            {
                "id": "upi",
                "icon": "💳",
                "severity": "high",
                "count": n,
                "title": f"{n} UPI payment activate karo",
                "why": "Customer ne pay kiya — manually plan activate karo (revenue ruka)",
                "impact": "activate karte hi customer ka product chalu",
                "cta_label": "UPI queue kholo",
                "cta_target": "sec-upi-selfserve",
            }
        )

    _sev = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: _sev.get(t.get("severity"), 9))
    total = sum(int(t.get("count") or 0) for t in tasks)
    high = sum(1 for t in tasks if t.get("severity") == "high")
    if not tasks:
        headline = "✅ Koi pending approval nahi — sab clear"
    else:
        headline = f"⚠️ {total} cheez aapki action maangti hai" + (
            f" ({high} urgent)" if high else ""
        )
    return {
        "ok": True,
        "enabled": True,
        "headline": headline,
        "your_tasks": tasks,
        "total_pending": total,
    }


@router.get("/office", summary="Admin Office — consolidated 'Sumit ke kaam' pending actions")
async def admin_office(_user=Depends(require_admin)):
    """Admin-side virtual-office: the 4 pending approval/action queues in ONE place.
    Read-only, never-500, gated ADMIN_OFFICE (default ON; '0' => disabled)."""
    import os

    if os.getenv("ADMIN_OFFICE", "1").strip().lower() in ("0", "false", "no", "off"):
        return {"ok": True, "enabled": False, "your_tasks": [], "total_pending": 0}
    return _admin_office()


@router.post("/upi/configure", summary="Set platform UPI VPA (data file — no container restart)")
async def upi_configure(body: UpiConfigureReq, _user=Depends(require_admin)):
    """Admin dashboard se UPI VPA save — ``data/platform_upi.json``. Env ``UPI_VPA`` still wins if set."""
    from app.platform import upi_config

    result = upi_config.set_vpa(body.vpa, set_by="admin_dashboard")
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "invalid VPA")
    try:
        from app.platform.team import log_event

        log_event(
            "kavya",
            "upi_configured",
            f"Platform UPI VPA set ({result.get('source', 'file')})",
            meta={"vpa_suffix": (body.vpa or "").split("@")[-1][:20]},
        )
    except Exception:
        pass
    return {"ok": True, "upi": upi_config.info()}


def _voice_primary_active() -> bool:
    try:
        from app.voice_agent.gemini_keys import runtime_voice_primary

        if runtime_voice_primary():
            return True
    except Exception:
        pass
    return (os.environ.get("VOICE_GEMINI_PRIMARY", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@router.get("/voice/gemini-keys", summary="Voice Gemini key pool status (masked)")
async def voice_gemini_keys_status(_user=Depends(require_admin)):
    from app.voice_agent import gemini_keys

    ks = gemini_keys.gemini_keys()
    return {
        "count": len(ks),
        "voice_primary": _voice_primary_active(),
        "keys_masked": [(k[:10] + "…") for k in ks],
    }


@router.post("/voice/gemini-keys", summary="Validate + save voice Gemini keys (no restart)")
async def voice_gemini_keys_set(body: VoiceGeminiKeysReq, _user=Depends(require_admin)):
    """Admin "Voice Keys" page se keys aati hain → HAR key test (live Gemini call) →
    sirf usable (200/429) keys pool me save (data/voice_gemini_keys.json) + reload →
    voice brain Gemini-first. No .env, no restart. Keys masked in response."""
    import httpx

    seen: set[str] = set()
    keys: list[str] = []
    for k in body.keys or []:
        k = (k or "").strip()
        if k and k not in seen:
            seen.add(k)
            keys.append(k)
    if not keys:
        raise HTTPException(status_code=400, detail="no keys provided")

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
    results = []
    usable: list[str] = []
    async with httpx.AsyncClient(timeout=15) as c:
        for i, k in enumerate(keys):
            try:
                r = await c.post(
                    url,
                    params={"key": k},
                    json={
                        "contents": [{"parts": [{"text": "hi"}]}],
                        "generationConfig": {"maxOutputTokens": 1},
                    },
                )
                s = r.status_code
            except Exception:
                s = 0
            ok = s in (200, 429)  # 429 = valid key, just throttled
            if ok:
                usable.append(k)
            tag = "valid" if s == 200 else ("throttled" if s == 429 else f"invalid({s or 'err'})")
            results.append({"index": i + 1, "masked": k[:10] + "…", "status": tag, "usable": ok})

    if not usable:
        raise HTTPException(status_code=400, detail="koi usable key nahi mili (sab invalid)")

    from app.voice_agent import gemini_keys

    state = gemini_keys.save_runtime_keys(usable, voice_primary=bool(body.voice_primary))
    try:
        from app.platform.team import log_event

        log_event(
            "arjun",
            "voice_gemini_keys_set",
            f"Voice Gemini pool set: {len(usable)}/{len(keys)} usable, primary={body.voice_primary}",
        )
    except Exception:
        pass
    return {
        "ok": True,
        "total": len(keys),
        "usable": len(usable),
        "results": results,
        "voice_primary": bool(body.voice_primary),
        "pool_size": state.get("count"),
    }


@router.get("/voice/self-test", summary="Built-in voice self-test (personas + stack + live)")
async def voice_self_test(
    _user=Depends(require_admin),
    personas: bool = True,
    stack: bool = True,
    live: bool = True,
    llm: bool = False,
    niche: str = "solar",
):
    """On-demand voice self-test — ek scorecard, abhi chala ke dekho.

    * ``personas`` — rule-based persona suite (FREE, no network, deterministic).
    * ``stack``    — live TTS/STT probes (LLM ping bhi jab ``llm=1`` → free-tier
      ka ek token jalega, isliye default OFF).
    * ``live``     — pichhli real calls ki quality (local transcripts).

    Network-probes off-loop + bounded; poora call ek hard deadline me wrapped hai
    taaki ek dead provider bhi admin-request ko hang na kare. Read-only — koi
    side-effect nahi (sirf ek best-effort team-event log hota hai)."""
    try:
        from app.voice_agent.self_test import run_voice_self_test

        report = await asyncio.wait_for(
            run_voice_self_test(
                personas=personas,
                stack=stack,
                live=live,
                llm=llm,
                niche=(niche or "solar"),
            ),
            timeout=180.0,
        )
        try:
            from app.platform.team import log_event

            log_event(
                "arjun",
                "voice_self_test",
                f"🩺 voice self-test {report.get('status')} score={report.get('score')}",
                status="ok" if report.get("ok") else "warn",
            )
        except Exception:
            pass
        return {"ok": bool(report.get("ok")), "report": report}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "self-test timed out"}
    except Exception as e:  # pragma: no cover - defensive
        return {"ok": False, "error": repr(e)[:200]}


@router.post("/upi/activate", summary="Activate plan after UPI screenshot verified")
async def upi_activate(
    body: UpiActivateReq,
    request: Request,
    _user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Admin ne WA screenshot dekha → plan activate."""
    cid = (body.client_id or "").strip()
    plan = (body.plan or "starter").strip().lower()
    if not cid:
        raise HTTPException(status_code=400, detail="client_id zaroori hai")
    try:
        from app.billing import usage as usage_mod
        from app.marketing import clients_store

        mrec = clients_store.resolve_client(cid)
        if not mrec:
            raise HTTPException(status_code=404, detail="client not found")
        mcid = str(mrec.get("id") or cid).strip()
        # Manual UPI payment verified by admin — ensure the Subscription row too
        # (portal /billing/subscription 404s without one; audit 2026-07-04).
        # ENTERPRISE FIX (2026-07-10): reset_usage_period ALSO call karo —
        # activate_plan sirf plan set karta tha, watermark reset nahi ho raha tha,
        # jisse minutes_used_this_period() pehle-wale-period ka lekar naya
        # customer ka quota turant khatam kar deta tha.
        usage_mod.activate_plan(cid, plan, ensure_subscription=True)
        usage_mod.reset_usage_period(cid)
        upd = {"plan": plan, "status": "active"}
        if body.clear_trial:
            upd["trial"] = False
        clients_store.update_client(mcid, **upd)
        # Dual-identity bind: when admin supplies the legacy billing/invoice owner
        # id (Jiya recreation case), attach it to this marketing client so portal
        # + billing alias resolution keep working. Idempotent; conflict-safe.
        legacy = str(body.billing_client_id or "").strip()
        if legacy:
            link_res = clients_store.link_billing_alias(mcid, legacy, actor="upi_activate")
            if not link_res.get("ok"):
                logger.warning(
                    "upi_activate alias link refused client=%s billing=%s reason=%s",
                    mcid,
                    legacy,
                    link_res.get("reason"),
                )
        # DELIVERY GUARANTEE (2026-07-05, council): paisa aate hi value-FIRST delivery
        # trigger karo (mini-site link + content) — customer ko "kuch nahi mila" na ho
        # (jiya makeover incident fix). Gated AUTO_DELIVER_VALUE: OFF = sirf detect+record
        # (dead-man sweep pakdega), ON = auto-send. Best-effort, never blocks activation.
        try:
            from app.marketing import customer_delivery

            fresh = clients_store.get_client(cid) or {}
            await customer_delivery.deliver_client_value(fresh)
        except Exception:
            pass
        try:
            from app.platform import customer_webhooks

            _payload = {
                "client_id": cid,
                "plan": plan,
                "gateway": "manual_upi",
                "currency": "INR",
                "activated_at": datetime.now(timezone.utc).isoformat(),
            }
            customer_webhooks.fire_emit(cid, "payment.received", {**_payload, "amount_inr": None})
            customer_webhooks.fire_emit(cid, "subscription.activated", _payload)
        except Exception:
            pass
        try:
            from app.platform.team import log_event

            log_event(
                "kavya",
                "upi_plan_activated",
                f"UPI manual activate: {cid} → {plan}",
                meta={"client_id": cid, "plan": plan, "via": "upi_screenshot"},
            )
        except Exception:
            pass
        # AUDIT — approving a payment is a money-path admin action; the team-log
        # above is informal/ephemeral, this is the formal tamper-record
        # /api/admin/audit-logs reads (best-effort — audit failure never blocks
        # the actual activation, mirrors impersonation.py's pattern).
        try:
            await log_audit(
                db,
                user_id=str(getattr(_user, "id", "")),
                action="payment.approve",
                resource_type="client",
                resource_id=cid,
                new_value={
                    "plan": plan,
                    "via": "upi_screenshot",
                    "clear_trial": bool(body.clear_trial),
                },
                ip_address=request.client.host if request.client else None,
                severity="warning",
            )
        except Exception as e:
            logger.warning(f"Audit log failed for UPI activation {cid}: {e}")
        return {"ok": True, "client_id": cid, "plan": plan}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:200]) from exc


@router.post(
    "/clients/{client_id}/deliver-now", summary="Human-clicked single-customer delivery unstick"
)
async def deliver_now(client_id: str, _user=Depends(require_admin)) -> dict:
    """Admin clicks this for one stuck paid customer — calls the existing
    deliver_client_value(force=True) bypass. Never touches AUTO_DELIVER_VALUE;
    always logs admin_manual_action either way so the reason is visible even
    on failure (no phone / send error / already delivered)."""
    from app.marketing import clients_store, customer_delivery, delivery_ledger

    client = clients_store.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="client not found")

    result = await customer_delivery.deliver_client_value(client, force=True)
    reason = result.get("skipped") or result.get("error")
    try:
        delivery_ledger.log_event(
            client_id,
            "admin_manual_action",
            detail=(reason or "delivered"),
            actor="admin",
        )
    except Exception as le:  # pragma: no cover
        logger.debug("deliver_now ledger log skip: %s", le)
    return {"ok": True, "delivered": bool(result.get("delivered")), "reason": reason}


@router.post("/clients/{client_id}/password-reset", summary="Admin-clicked customer password reset")
async def client_password_reset(client_id: str, body: dict, _user=Depends(require_admin)) -> dict:
    password = body.get("password")
    # ADR-104 (2026-07-15, Priority 4): backend minimum now matches the
    # admin_dashboard.html modal's own client-side rule (8 chars) -- the API
    # previously only enforced 4, so a direct call (bypassing the UI) could
    # set a materially weaker password than the UI ever allows.
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    from app.marketing import clients_store

    client = clients_store.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    email = client.get("email")
    if not email:
        raise HTTPException(
            status_code=400, detail="Client email not set, cannot reset login credentials"
        )

    from app.api import customer_auth

    customer_auth.register_login(email, password, client_id)
    # ADR-104 (2026-07-15, Priority 4): this endpoint had no audit trail at
    # all -- a real customer's login credential could be overwritten with no
    # record of who did it or when. Mirrors the existing deliver_now pattern
    # (delivery_ledger.log_event, per-client, actor="admin"). Never the
    # password itself -- only that a reset happened.
    try:
        from app.marketing import delivery_ledger

        delivery_ledger.log_event(
            client_id, "admin_manual_action", detail="password_reset", actor="admin"
        )
    except Exception as le:  # pragma: no cover
        logger.debug("password_reset ledger log skip: %s", le)
    return {"ok": True}


@router.post(
    "/clients/{client_id}/onboard/scrape", summary="Admin-clicked customer website re-scrape"
)
async def client_onboard_scrape(
    client_id: str, background_tasks: BackgroundTasks, _user=Depends(require_admin)
) -> dict:
    from app.marketing import clients_store

    client = clients_store.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    from app.marketing import onboarding

    background_tasks.add_task(onboarding.auto_onboard, client_id, send_welcome=False, force=True)
    # ADR-104 (2026-07-15, Priority 4): force=True re-scrapes the client's
    # real website and re-seeds KB/content pack even if setup_done -- a real
    # overwrite-capable action with no prior audit trail. Log it the same way
    # as deliver_now/password_reset (fire-and-forget, never blocks the
    # background task or the response).
    try:
        from app.marketing import delivery_ledger

        delivery_ledger.log_event(
            client_id, "admin_manual_action", detail="onboard_rescrape_triggered", actor="admin"
        )
    except Exception as le:  # pragma: no cover
        logger.debug("onboard_scrape ledger log skip: %s", le)
    return {"ok": True}


@router.get("/upi/clients", summary="Search clients for manual UPI activate")
async def upi_clients_search(q: str = "", limit: int = 20, _user=Depends(require_admin)):
    """God Mode — client id / naam / phone se dhoondo."""
    try:
        from app.marketing import clients_store

        needle = (q or "").strip().lower()
        rows = clients_store.list_clients()
        out: list[dict] = []
        for c in rows:
            cid = str(c.get("id") or "")
            name = str(c.get("business_name") or "")
            phone = str(c.get("phone") or "")
            plan = str(c.get("plan") or "trial").lower()
            hay = f"{cid} {name} {phone}".lower()
            if needle and needle not in hay:
                continue
            out.append(
                {
                    "client_id": cid,
                    "business_name": name,
                    "phone": phone,
                    "plan": plan,
                    "trial": bool(c.get("trial")),
                }
            )
            if len(out) >= max(1, min(limit, 50)):
                break
        return {"clients": out, "count": len(out)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:120]) from exc


@router.get("/trust/status", summary="Turnstile + Sentry + PostHog armed status")
async def trust_status(_user=Depends(require_admin)):
    from app.platform import posthog_config, trust_config

    return {"ok": True, **trust_config.status(), "posthog": posthog_config.status()}


@router.post("/trust/configure-turnstile", summary="Set Turnstile keys (no restart)")
async def trust_configure_turnstile(body: TrustTurnstileReq, _user=Depends(require_admin)):
    from app.platform import trust_config

    result = trust_config.set_turnstile(
        site_key=body.site_key, secret_key=body.secret_key, set_by="admin_dashboard"
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "save failed")
    try:
        from app.platform.team import log_event

        log_event("kavya", "turnstile_configured", "Turnstile armed via admin (file)", meta={})
    except Exception:
        pass
    return {"ok": True, "trust": trust_config.status()}


@router.post(
    "/trust/configure-sentry", summary="Set Sentry DSN (lazy web init; worker restart recommended)"
)
async def trust_configure_sentry(body: TrustSentryReq, _user=Depends(require_admin)):
    from app.platform import trust_config

    result = trust_config.set_sentry_dsn(body.dsn, set_by="admin_dashboard")
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "save failed")
    return {"ok": True, "trust": trust_config.status(), **result}


@router.post("/trust/configure-posthog", summary="Set PostHog API key + host (no restart)")
async def trust_configure_posthog(body: TrustPosthogReq, _user=Depends(require_admin)):
    from app.platform import posthog_config, trust_config

    result = posthog_config.set_posthog(
        api_key=body.api_key, host=body.host or "", set_by="admin_dashboard"
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "save failed")
    try:
        from app.platform.team import log_event

        log_event("kavya", "posthog_configured", "PostHog armed via admin (file)", meta={})
    except Exception:
        pass
    return {
        "ok": True,
        "trust": {**trust_config.status(), "posthog": posthog_config.status()},
        **result,
    }


@router.post(
    "/flow/seed-templates", summary="Apply all Flow Runner starter templates (FLOW_RUNNER=1)"
)
async def flow_seed_templates(_user=Depends(require_admin)):
    """Council ship-now — 3 starter flows ek click me (draft-safe)."""
    if os.getenv("FLOW_RUNNER", "0") not in ("1", "true", "True"):
        raise HTTPException(
            status_code=503,
            detail="FLOW_RUNNER disabled — docker-compose / .env me FLOW_RUNNER=1 set karo",
        )
    from app.automation import flow_compiler, flow_store, flow_templates

    created: list[dict] = []
    for tpl in flow_templates.list_templates():
        tid = tpl.get("tid") or ""
        body = flow_templates.to_flow(tid)
        if not body:
            continue
        saved = flow_store.save_flow(body, by="admin_seed")
        if not saved.get("ok"):
            continue
        _proc, errs, kind = flow_compiler.compile_flow(saved["flow"])
        created.append(
            {
                "tid": tid,
                "flow_id": (saved.get("flow") or {}).get("id"),
                "name": tpl.get("name"),
                "runnable": not errs,
                "kind": kind,
            }
        )
    return {"ok": True, "created": created, "count": len(created)}


@router.get(
    "/voice/latency", summary="Voice agent per-turn latency rollup (P50/P95) — proves call speed"
)
async def voice_latency(date: str = "", recent: int = 20, _user=Depends(require_admin)):
    """Per-turn voice latency (stt_ms / llm_first_ms / tts_first_ms / turn_ms)
    rolled up to P50/P95/avg/max from ``data/turn_metrics/`` — the numbers that
    prove (and let us tune) call speed vs the sub-700ms SOTA bar.

    ``TURN_METRICS`` (default ON) writes one line per real turn on every live
    Vobiz/phone/web call. ``date`` = 'YYYY-MM-DD' (UTC; default today). ``recent``
    = how many latest turns to return for drill-down (max 200). Never raises."""
    from app.voice_agent import turn_metrics

    day = (date or "").strip() or None
    records = turn_metrics.load_day(day)
    summary = turn_metrics.rollup(records)
    recent_n = max(0, min(int(recent or 0), 200))
    tail = records[-recent_n:] if recent_n else []
    return {
        "ok": True,
        "date": day or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": summary,
        "recent": tail,
        "metrics_enabled": turn_metrics.enabled(),
    }


@router.get("/voice/bookings", summary="Appointments the AI voice agent booked (durable ledger)")
async def voice_bookings(date: str = "", limit: int = 50, _user=Depends(require_admin)):
    """Recent appointments booked on AI calls, from the durable ledger
    (``data/bookings/``). This is the proof that "AI books the meeting" is real —
    each booking persists across restarts and the owner is notified on booking.
    ``date`` = 'YYYY-MM-DD' (default today). Never raises."""
    from app.integrations.calendar_booking import get_calendar

    cal = get_calendar()
    day = (date or "").strip() or None
    items = cal.list_bookings(limit=max(1, min(int(limit or 50), 500)), date_str=day)
    return {
        "ok": True,
        "date": day or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "count": len(items),
        "bookings": items,
        "provider": getattr(cal, "provider", "internal"),
        "config": cal.validate_config(),
    }
