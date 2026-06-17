"""
Admin Ops API
=============
POST /api/admin/campaign/launch  → outbound call campaign fire karo (fire_calls.py)
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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["Admin Ops"])

_BASE = "/app" if os.path.isdir("/app") else os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)
_CAMPAIGN_KEY = "admin:campaign:last_run"

# ── Redis (optional; graceful skip) ─────────────────────────────────────────
_r: Optional[object] = None


def _redis() -> Optional[object]:
    global _r
    if _r is not None:
        return _r
    try:
        import redis as _redis_lib

        url = (os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()
        client = _redis_lib.Redis.from_url(
            url, socket_connect_timeout=2, decode_responses=True
        )
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
    niche: Optional[str] = None


# ── Campaign endpoints ────────────────────────────────────────────────────────
@router.post("/campaign/launch", summary="Launch outbound call campaign")
async def launch_campaign(req: CampaignLaunchReq, _user=Depends(require_admin)):
    """
    Fires fire_calls.py in background (asyncio subprocess).
    Returns immediately; poll /api/admin/campaign/status for result.
    TRAI 10am-7pm gate is enforced inside fire_calls.py itself.
    """
    if not 1 <= req.limit <= 200:
        raise HTTPException(status_code=400, detail="limit must be 1–200")

    script = os.path.join(_BASE, "scripts", "fire_calls.py")
    if not os.path.isfile(script):
        raise HTTPException(status_code=500, detail="fire_calls.py not found in container")

    cmd = [sys.executable, script, "--limit", str(req.limit)]
    if req.dry_run:
        cmd.append("--dry-run")
    if req.niche:
        cmd.extend(["--niche", req.niche])

    _redis_set(
        _CAMPAIGN_KEY,
        {
            "status": "running",
            "limit": req.limit,
            "dry_run": req.dry_run,
            "niche": req.niche,
            "started_at": time.time(),
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
                },
            )

    asyncio.create_task(_run_bg())

    return {
        "queued": True,
        "limit": req.limit,
        "dry_run": req.dry_run,
        "poll": "/api/admin/campaign/status",
    }


@router.get("/campaign/status", summary="Last campaign run status")
async def campaign_status(_user=Depends(require_admin)):
    """Poll this after launch. status: running | done | error | timeout | never_run"""
    st = _redis_get(_CAMPAIGN_KEY)
    return st if st else {"status": "never_run"}


# ── System summary ────────────────────────────────────────────────────────────
@router.get("/system/summary", summary="System snapshot for God Mode panel")
async def system_summary(_user=Depends(require_admin)):
    """
    Aggregates activation readiness, Razorpay, TRAI window, telephony score,
    provider flags, and last campaign status for the admin God Mode panel.
    """
    import datetime

    readiness: dict = {}
    try:
        from app.api.activation import activation_summary_public

        readiness = await activation_summary_public()
    except Exception as exc:
        readiness = {"error": str(exc)}

    rzp_key = os.environ.get("RAZORPAY_KEY_ID", "")
    rzp_ok = bool(
        rzp_key
        and not rzp_key.startswith("rzp_test_you")
        and not rzp_key.startswith("your-")
    )
    rzp_live = rzp_key.startswith("rzp_live_") if rzp_ok else False

    ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    trai_start = int(os.environ.get("COMPLIANCE_PROMO_START", "10").split(":")[0])
    trai_end = int(os.environ.get("COMPLIANCE_PROMO_END", "19").split(":")[0])
    calling_open = trai_start <= ist_now.hour < trai_end

    last_campaign = _redis_get(_CAMPAIGN_KEY) or {"status": "never_run"}

    flags = {
        "VOBIZ_CALL_RECORD": bool(int(os.environ.get("VOBIZ_CALL_RECORD", "0"))),
        "AUTO_EMAIL_OUTREACH": os.environ.get("AUTO_EMAIL_OUTREACH", "").lower()
        in ("1", "true"),
        "REPLY_AGENT": os.environ.get("REPLY_AGENT", "").lower() in ("1", "true"),
        "SELF_IMPROVE_LOOP": os.environ.get("SELF_IMPROVE_LOOP", "").lower()
        in ("1", "true"),
        "PLAN_RATE_LIMIT": bool(int(os.environ.get("PLAN_RATE_LIMIT", "0"))),
        "SALES_TEAM": os.environ.get("SALES_TEAM", "").lower() in ("1", "true"),
        "GROWTH_OPTIMIZER": os.environ.get("GROWTH_OPTIMIZER", "").lower()
        in ("1", "true"),
        "GROQ_STT": bool(os.environ.get("GROQ_API_KEY", "").strip()),
        "EXOTEL_CREDS": bool(
            os.environ.get("EXOTEL_SID")
            and (
                os.environ.get("EXOTEL_API_KEY")
                or os.environ.get("EXOTEL_API_TOKEN")
            )
            and os.environ.get("EXOTEL_CALLER_ID")
        ),
    }

    telephony = readiness.get("telephony") or {}
    provider = (
        os.environ.get("TELEPHONY_PROVIDER")
        or os.environ.get("DEFAULT_TELEPHONY")
        or "exotel"
    )

    return {
        "readiness": readiness,
        "razorpay": {
            "key_set": rzp_ok,
            "live_key": rzp_live,
            "key_prefix": rzp_key[:12] + "…" if rzp_key else "UNSET",
        },
        "trai": {
            "calling_open": calling_open,
            "window": f"{trai_start:02d}:00–{trai_end:02d}:00 IST",
            "ist_hour": ist_now.hour,
        },
        "telephony_provider": provider,
        "exotel_caller_id": os.environ.get("EXOTEL_CALLER_ID", "unset"),
        "telephony_score": telephony.get("score", 0),
        "telephony_missing": telephony.get("missing", []),
        "telephony_actions": telephony.get("actions", []),
        "ready_for_calling": readiness.get("ready_for_calling", False),
        "last_campaign": last_campaign,
        "flags": flags,
        "generated_at": ist_now.strftime("%H:%M IST"),
    }
