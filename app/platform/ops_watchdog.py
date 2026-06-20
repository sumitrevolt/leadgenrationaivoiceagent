"""AI Ops Watchdog — autonomous monitoring + AI diagnosis + proactive alerting.

THE missing ops automation: the stack self-runs (scheduler, agents, outreach), but if a
job silently stops or an LLM provider goes down, nobody knows. This is the agentic-AIOps
loop — **sense → reason → alert** (2026 best practice): collect health signals, detect
anomalies by rules, let free_ai diagnose them in Hinglish, and EMAIL Sumit when something
needs a human. Throttled per-issue so it never spams.

Heartbeat pattern: the scheduler already touches `data/.scheduler.lock` every tick; a stale
lock means jobs have stopped. Output-file freshness (digest) tells us dailies ran.

OFF by default + never-crash. Enable `OPS_WATCHDOG=1`. Alerts need `notify_email` + SMTP
configured (else it just logs). Runs hourly via the team scheduler.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = os.path.join("data", ".scheduler.lock")
_ALERT_STATE = os.path.join("data", ".watchdog_alert.json")
_ALERT_COOLDOWN_H = 6


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _age_min(path: str):
    try:
        return (
            round((time.time() - os.path.getmtime(path)) / 60, 1) if os.path.exists(path) else None
        )
    except Exception:
        return None


def _signals() -> dict[str, Any]:
    s: dict[str, Any] = {}
    s["scheduler_age_min"] = _age_min(_LOCK)
    # LLM providers
    try:
        from app.voice_agent import free_ai

        d = free_ai.describe() or {}
        provs = d.get("providers", d) if isinstance(d, dict) else {}
        provs = provs if isinstance(provs, dict) else {}
        s["providers"] = provs
        s["any_llm"] = any(bool(v) for v in provs.values()) if provs else None
    except Exception:
        s["any_llm"] = None
    # disk
    try:
        du = shutil.disk_usage("/")
        s["disk_pct"] = round(du.used / du.total * 100, 1)
    except Exception:
        s["disk_pct"] = None
    # db present
    try:
        for p in ("leadgen.db", "/opt/leadgen/leadgen.db"):
            if os.path.exists(p):
                s["db_kb"] = round(os.path.getsize(p) / 1024, 1)
                break
    except Exception:
        pass
    # daily digest freshness (did the 08:30 job run?)
    digest_age = _age_min(os.path.join("data", "daily_digest.txt"))
    s["digest_age_h"] = round(digest_age / 60, 1) if digest_age is not None else None
    return s


def _detect(s: dict[str, Any]) -> list[dict]:
    issues: list[dict] = []
    age = s.get("scheduler_age_min")
    if age is not None and age > 20:
        issues.append(
            {
                "key": "scheduler_stalled",
                "sev": "critical",
                "msg": f"Scheduler heartbeat {age} min purana — automation ruk gaya ho sakta hai",
            }
        )
    if s.get("any_llm") is False:
        issues.append(
            {
                "key": "llm_down",
                "sev": "critical",
                "msg": "Koi LLM provider available nahi (key/quota) — AI features down",
            }
        )
    dp = s.get("disk_pct")
    if dp is not None and dp > 90:
        issues.append({"key": "disk_high", "sev": "warning", "msg": f"Disk {dp}% bhar gaya"})
    dh = s.get("digest_age_h")
    if dh is not None and dh > 30:
        issues.append(
            {
                "key": "digest_stale",
                "sev": "warning",
                "msg": f"Daily digest {dh}h purana — 08:30 wala job shayad nahi chala",
            }
        )
    return issues


async def _diagnose(issues: list[dict], signals: dict) -> str:
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            system="Tu ek senior SRE hai. In system issues ka 2-line Hinglish summary + sabse "
            "zaroori ek action de. Concise.",
            messages=[
                {
                    "role": "user",
                    "content": json.dumps({"issues": issues, "signals": signals})[:1500],
                }
            ],
            max_tokens=120,
            temperature=0.2,
        )
        return (reply or "").strip()
    except Exception:
        return ""


def _should_alert(key: str) -> bool:
    try:
        state = json.load(open(_ALERT_STATE)) if os.path.exists(_ALERT_STATE) else {}
    except Exception:
        state = {}
    if time.time() - float(state.get(key, 0)) < _ALERT_COOLDOWN_H * 3600:
        return False
    state[key] = time.time()
    try:
        os.makedirs(os.path.dirname(_ALERT_STATE), exist_ok=True)
        json.dump(state, open(_ALERT_STATE, "w"))
    except Exception:
        pass
    return True


async def _alert(subject: str, body: str) -> bool:
    # Phone push bhi (self-hosted ntfy, gated NTFY_URL/TOPIC — best-effort).
    try:
        from app.integrations import ntfy

        await ntfy.push(subject, body[:1500], priority="high", tags=["rotating_light"])
    except Exception:
        pass
    try:
        from app.config import settings

        to = (getattr(settings, "notify_email", "") or os.getenv("NOTIFY_EMAIL", "")).strip()
        if not to:
            return False
        from app.integrations.email_sender import EmailSender

        return bool(await EmailSender().send_email([to], subject, body))
    except Exception as exc:
        logger.info("watchdog alert failed: %s", exc)
        return False


def _log(kind: str, detail: str) -> None:
    try:
        from app.platform.team import log_event

        log_event("kavya", kind, detail)
    except Exception:
        pass


async def run_watchdog() -> dict[str, Any]:
    """Sense → detect → diagnose → alert. Always returns a report dict. Never raises."""
    if not _flag("OPS_WATCHDOG"):
        return {"skipped": "OPS_WATCHDOG off"}
    try:
        # Outbox flush — failed outbound-webhook deliveries ko TIME-based retry (event-traffic
        # ke bina bhi, e.g. raat me). Best-effort — watchdog ko kabhi block/break nahi karta.
        try:
            from app.platform import outbound_webhooks as _ow

            await _ow.retry_pending()
        except Exception:
            pass
        s = _signals()
        issues = _detect(s)
        report: dict[str, Any] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "ok": not issues,
            "signals": s,
            "issues": issues,
            "alerted": [],
        }
        if issues:
            diag = await _diagnose(issues, s)
            report["diagnosis"] = diag
            for i in issues:
                if i["sev"] == "critical" and _should_alert(i["key"]):
                    sent = await _alert(
                        f"[LeadGen ALERT] {i['key']}",
                        f"{i['msg']}\n\nAI diagnosis: {diag or '(n/a)'}\n\nSignals: {json.dumps(s, ensure_ascii=False)}",
                    )
                    if sent:
                        report["alerted"].append(i["key"])
            _log(
                "watchdog_issues", f"{len(issues)} issue(s): " + ", ".join(i["key"] for i in issues)
            )
        return report
    except Exception as exc:
        logger.info("run_watchdog err: %s", exc)
        return {"error": str(exc)}


__all__ = ["run_watchdog"]
