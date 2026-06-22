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

# Known integration names (free-form bhi chalta — yeh sirf docs/UI ordering)
KNOWN = (
    "smtp",
    "email_api",
    "imap",
    "exotel",
    "twilio",
    "places",
    "whatsapp",
    "pollinations",
    "qdrant",
    "razorpay",
    "stripe",
)


def _enabled() -> bool:
    return os.environ.get("INTEGRATION_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def _alert_n() -> int:
    try:
        return max(1, int(os.environ.get("INTEGRATION_FAIL_ALERT_N", str(DEFAULT_ALERT_N))))
    except Exception:
        return DEFAULT_ALERT_N


def _redis():
    import redis as _redis

    from app.config import settings

    return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)


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


def snapshot(hours: int = 24) -> dict[str, Any]:
    """Pichle N ghante ke per-integration fail/ok counts + last errors. Never raise."""
    out: dict[str, Any] = {
        "hours": hours,
        "integrations": {},
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        r = _redis()
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
        out["error"] = str(e)[:120]
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
