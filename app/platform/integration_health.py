"""Integration silent-failure counters + alert (SMTP/Places/Qdrant...).

PROBLEM: zyada-tar integration hooks best-effort try/except hain (sahi design —
prod kabhi girna nahi chahiye), PAR fail hone pe sirf ek log line aati hai.
SMTP creds expire ho jayein ya koi API girne lage to hafton pata nahi chalta
("emails ja rahe honge" maan ke baithe rehte).

YEH MODULE: ultra-light counters — integrations apni failure/success
`record_failure("smtp", note)` / `record_success("smtp")` se report karte
(Redis hourly buckets, 26h TTL; Redis down = silent skip, hot-path pe ZERO
load). Watchdog (hourly) `run_watch()`: pichle ~1h me kisi integration ke
fails >= threshold (env `INTEGRATION_FAIL_ALERT_N`, default 5) to email
alert — gated `INTEGRATION_ALERTS=1` (off = sirf counters,
`GET /api/growth/infra/integrations` se inspect). Per-integration alert
dedupe 6h. Import-safe, KABHI raise nahi. (automation_health pattern.)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PREFIX = "integ"
_BUCKET_TTL_S = 26 * 3600
_DEDUPE_TTL_S = 6 * 3600
DEFAULT_ALERT_N = 5
DEFAULT_PLACES_QUOTA_COOLDOWN_S = 24 * 3600

# Known integration names (free-form bhi chalta — yeh sirf docs/UI ordering)
KNOWN = (
    "smtp",
    "email_api",
    "imap",
    "vobiz",  # active telephony provider — zero-media relay flakes (audit 2026-07-04)
    "places",
    "whatsapp",
    "pollinations",
    "qdrant",
    "stripe",  # Removed 2026-07-10 — integration provider entrypoint retained for graceful skip
)


def _enabled() -> bool:
    return os.environ.get("INTEGRATION_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def _alert_n() -> int:
    try:
        return max(1, int(os.environ.get("INTEGRATION_FAIL_ALERT_N", str(DEFAULT_ALERT_N))))
    except Exception:
        return DEFAULT_ALERT_N


def _redis_mode() -> str:
    """Explicit test-mode policy. Prod default = enabled. Hermetic tests set
    `INTEGRATION_HEALTH_REDIS_MODE=disabled` to make snapshot() perform zero
    network I/O. Invalid values fail safe (treated as enabled — never silently
    disabled in production)."""
    v = os.environ.get("INTEGRATION_HEALTH_REDIS_MODE", "").strip().lower()
    if v == "disabled":
        return "disabled"
    return "enabled"


def _redis():
    """Bounded Redis client. `socket_connect_timeout=1.0` + `socket_timeout=1.0`
    caps both connect + read at 1s each (was: socket_timeout=2 but NO connect
    timeout → blocked forever if Redis absent). No retry — a single fast-fail
    is safer for the health-snapshot path than exponential backoff.

    Fail-fast rationale (2026-07-11 hardening): the previous configuration
    hung the full pytest suite because `sock.connect(socket_address)` had no
    upper bound. Bounding it here lets a Redis outage degrade the snapshot to
    a `"redis_unavailable"` diagnostic within seconds instead of hanging any
    caller (customer dashboards / /health / test suite)."""
    import redis as _redis

    from app.config import settings

    return _redis.Redis.from_url(
        str(settings.redis_url),
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        retry_on_timeout=False,
    )


def _hour_key(dt: datetime | None = None, kind: str = "fail") -> str:
    dt = dt or datetime.now(timezone.utc)
    return f"{_PREFIX}:{kind}:{dt.strftime('%Y%m%d%H')}"


def record_failure(integration: str, note: str = "") -> None:
    """Integration failure count karo. FAST + KABHI raise nahi (hot-path safe)."""
    try:
        r = _redis()
        k = _hour_key()
        name = (integration or "?")[:30]
        r.hincrby(k, name, 1)
        r.expire(k, _BUCKET_TTL_S)
        if note:
            # last error note (debugging) — ek hi key, overwrite ok
            r.setex(f"{_PREFIX}:lasterr:{name}", _BUCKET_TTL_S, str(note)[:200])
    except Exception:
        pass


def record_success(integration: str) -> None:
    """Success bhi count karo (ok-rate visible). KABHI raise nahi."""
    try:
        r = _redis()
        k = _hour_key(kind="ok")
        r.hincrby(k, (integration or "?")[:30], 1)
        r.expire(k, _BUCKET_TTL_S)
    except Exception:
        pass


def places_quota_cooldown_remaining() -> int:
    """Shared Places quota cooldown ka bacha hua time seconds me do."""
    try:
        ttl = int(_redis().ttl(f"{_PREFIX}:cooldown:places"))
        return max(0, ttl)
    except Exception:
        return 0


def start_places_quota_cooldown(seconds: int | None = None) -> None:
    """Places 429 ke baad cross-worker retry storm rok do. Never raises."""
    try:
        configured = int(os.environ.get("PLACES_QUOTA_COOLDOWN_S", DEFAULT_PLACES_QUOTA_COOLDOWN_S))
    except Exception:
        configured = DEFAULT_PLACES_QUOTA_COOLDOWN_S
    ttl = seconds if seconds is not None else configured
    ttl = max(300, min(int(ttl), 24 * 3600))
    try:
        _redis().setex(f"{_PREFIX}:cooldown:places", ttl, "quota_exhausted")
    except Exception:
        pass


def snapshot(hours: int = 24) -> dict[str, Any]:
    """Pichle N ghante ke per-integration fail/ok counts + last errors.

    Never raises. Redis absent OR test-mode disabled → returns a
    `redis_status: "unavailable" | "disabled"` diagnostic instead of blocking
    or silently returning an empty-but-healthy-looking dict (2026-07-11
    hardening — closes the full-suite hang from `r.hgetall` blocking on
    `socket.connect` when Redis was not running).
    """
    import time as _time

    _t0 = _time.monotonic()
    out: dict[str, Any] = {
        "hours": hours,
        "integrations": {},
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "redis_status": "healthy",
    }

    # Explicit test-mode guard — production default is enabled.
    if _redis_mode() == "disabled":
        out["redis_status"] = "disabled"
        out["degraded"] = True
        out["reason"] = "INTEGRATION_HEALTH_REDIS_MODE=disabled"
        out["elapsed_s"] = round(_time.monotonic() - _t0, 3)
        return out

    # Bounded acquisition. If the constructor OR the very first Redis command
    # fails/times out, degrade the snapshot immediately — do NOT loop.
    try:
        r = _redis()
        # Force a bounded ping so we know the connection is usable before
        # entering the per-hour hgetall loop. If ping fails, we degrade
        # gracefully instead of chasing 24 more failing hgetall calls.
        try:
            r.ping()
        except Exception as _ping_exc:
            out["redis_status"] = "unavailable"
            out["degraded"] = True
            out["reason"] = "connection_failed"
            out["error_type"] = type(_ping_exc).__name__[:60]
            out["elapsed_s"] = round(_time.monotonic() - _t0, 3)
            logger.debug("integration_health: redis unavailable (%s)", type(_ping_exc).__name__)
            return out
        now = datetime.now(timezone.utc)
        agg: dict[str, dict[str, int]] = {}
        for i in range(max(1, min(hours, 26))):
            dt = now - timedelta(hours=i)
            for kind in ("fail", "ok"):
                try:
                    h = r.hgetall(_hour_key(dt, kind)) or {}
                except Exception:
                    h = {}
                for name_b, cnt_b in h.items():
                    name = name_b.decode() if isinstance(name_b, bytes) else str(name_b)
                    d = agg.setdefault(name, {"fail": 0, "ok": 0})
                    try:
                        d[kind] += int(cnt_b)
                    except Exception:
                        pass
        for name, d in agg.items():
            total = d["fail"] + d["ok"]
            last_err = None
            try:
                v = r.get(f"{_PREFIX}:lasterr:{name}")
                last_err = (v.decode() if isinstance(v, bytes) else v) if v else None
            except Exception:
                pass
            out["integrations"][name] = {
                "fail": d["fail"],
                "ok": d["ok"],
                "fail_rate": round(d["fail"] / total, 3) if total else None,
                "last_error": last_err,
            }
    except Exception as e:
        # Sanitize: expose only exception TYPE, never the message (may contain
        # Redis URL with credentials — logger.redact_message covers formatted
        # log lines but not dict values placed into a JSON response).
        out["redis_status"] = "unavailable"
        out["degraded"] = True
        out["reason"] = "acquisition_failed"
        out["error_type"] = type(e).__name__[:60]
    out["elapsed_s"] = round(_time.monotonic() - _t0, 3)
    return out


def _recent_fails(r) -> dict[str, int]:
    """Current + previous hour ke fails (watchdog hourly chalta — gap-proof)."""
    now = datetime.now(timezone.utc)
    agg: dict[str, int] = {}
    for dt in (now, now - timedelta(hours=1)):
        try:
            h = r.hgetall(_hour_key(dt)) or {}
        except Exception:
            h = {}
        for name_b, cnt_b in h.items():
            name = name_b.decode() if isinstance(name_b, bytes) else str(name_b)
            try:
                agg[name] = agg.get(name, 0) + int(cnt_b)
            except Exception:
                pass
    return agg


async def run_watch() -> dict[str, Any]:
    """Watchdog hook: failing integrations → (gated) alert. KABHI raise nahi."""
    out: dict[str, Any] = {"enabled": _enabled(), "alerted": []}
    try:
        r = _redis()
        fails = _recent_fails(r)
        threshold = _alert_n()
        hot = {k: v for k, v in fails.items() if v >= threshold}
        out["recent_fails"] = fails
        if not hot:
            return out
        if not _enabled():
            logger.warning(f"[integration_health] failing (alerts OFF): {hot}")
            return out
        for name, cnt in hot.items():
            # dedupe: ek integration pe 6h me ek hi alert
            try:
                if not r.set(f"{_PREFIX}:alerted:{name}", "1", nx=True, ex=_DEDUPE_TTL_S):
                    continue
            except Exception:
                pass
            last_err = ""
            try:
                v = r.get(f"{_PREFIX}:lasterr:{name}")
                last_err = (v.decode() if isinstance(v, bytes) else str(v)) if v else ""
            except Exception:
                pass
            subject = f"⚠️ Integration FAILING: {name} ({cnt} fails/hr)"
            body = (
                f"Integration '{name}' pichle ~1h me {cnt} baar fail hua "
                f"(threshold {threshold}).\n\nLast error: {last_err or 'n/a'}\n\n"
                "Creds/quota/network check karo. Snapshot: GET /api/growth/infra/integrations\n"
                "(integration_health watchdog)"
            )
            sent = False
            notify = os.environ.get("NOTIFY_EMAIL", "").strip()
            # NOTE: smtp khud fail ho raha ho to yeh alert email bhi nahi jayega —
            # last-resort try anyway (chahe smtp failing ho).
            if notify and name not in ("smtp", "email_api"):
                try:
                    from app.integrations.email_sender import email_sender

                    sent = await email_sender.send_email([notify], subject, body)
                except Exception:
                    sent = False
            if not sent and notify:
                # last resort: email try karo chahe smtp hi failing ho
                try:
                    from app.integrations.email_sender import email_sender

                    await email_sender.send_email([notify], subject, body)
                except Exception:
                    pass
            out["alerted"].append({"integration": name, "fails": cnt})
        if out["alerted"]:
            try:
                from app.platform import team

                team.log_event(
                    "kavya",
                    "integration_health",
                    f"alerted: {[a['integration'] for a in out['alerted']]}",
                    status="warn",
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[integration_health] run_watch failed: {e}")
        out["error"] = str(e)[:120]
    return out
