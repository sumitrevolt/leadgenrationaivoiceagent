"""ops_alerts.py — turn the new F-track signals into actual notifications.

After the F.1-F.5 + C-track deploy the modules existed but **nothing told the
operator when they fired**. Engineer-agent scores dropped silently; eval_gate
rejected silently; activation-readiness blockers appeared silently. This module
closes that loop with three thin, idempotent alert helpers wired into the
existing ntfy push channel.

Design:
- **Single master flag** `OPS_ALERTS=1` — OFF default = no notifications,
  zero behaviour change vs today. Once on, individual alerts still respect
  their own thresholds + cooldowns so the operator's phone doesn't buzz on
  every benign blip.
- **Cooldown jsonl** at `data/ops_alerts_state.jsonl` records the last fire
  time per alert key. Re-firing requires the cooldown to elapse — no alert
  storms when a metric oscillates around a threshold.
- **Fire-and-forget**: every helper schedules the ntfy push via
  `ntfy.push_bg()` so the caller (engineer-agent run, eval_gate.score_and_gate,
  scheduler tick) is never blocked or broken by alert plumbing.
- **Never raises**: ntfy unset, file IO error, anything = silent no-op.

Wiring:
    engineer_agents.run_X() result -> maybe_alert_engineer_score(role, score)
    eval_gate.score_and_gate(...)  -> maybe_alert_eval_reject(suite, metric, verdict)
    scheduler 08:30 IST job        -> daily_readiness_digest()
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "OPS_ALERTS"
_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_STATE_PATH = _DATA_DIR / "ops_alerts_state.jsonl"

# Cooldowns (seconds) per alert kind — picked to balance signal and noise.
_COOLDOWN = {
    "engineer_score": 4 * 3600,  # at most one per role per 4h
    "eval_reject": 6 * 3600,  # at most one per suite/metric per 6h
    "readiness_digest": 20 * 3600,  # at most one daily-style digest per 20h
    "webhook_dead_letter": 6 * 3600,  # at most one per webhook per 6h (L.3)
    "compliance_disabled": 1 * 3600,  # legal kill-switch page, at most one per 1h
    "payment_failed": 1 * 3600,  # payment-failure page, at most one per 1h
    "smtp_disabled": 2 * 3600,  # SMTP account-block page, at most one per 2h
    "paid_customer_stuck": 3
    * 3600,  # jiya-class ghosting bug — page founder, at most one per client per 3h
}

# Thresholds — override via env if the operator wants tighter/looser.
_ENG_THRESHOLD = float(os.environ.get("OPS_ALERT_ENGINEER_THRESHOLD", "60"))
_EVAL_REJECT_BURST = int(os.environ.get("OPS_ALERT_EVAL_REJECT_BURST", "3"))
_EVAL_REJECT_WINDOW_SEC = int(os.environ.get("OPS_ALERT_EVAL_REJECT_WINDOW", str(24 * 3600)))


def enabled() -> bool:
    """Master gate. OFF default = INERT."""
    return os.environ.get(_FLAG, "0").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# Cooldown ledger — append-only jsonl, tail-read.
# --------------------------------------------------------------------------- #
def _ensure_dir() -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _read_state() -> dict[str, float]:
    """Latest fire-time per alert key. {} on missing/error."""
    if not _STATE_PATH.exists():
        return {}
    try:
        latest: dict[str, float] = {}
        for line in _STATE_PATH.read_text(encoding="utf-8").splitlines()[-500:]:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                k = str(rec.get("key", ""))
                ts = float(rec.get("ts", 0.0))
                if k:
                    latest[k] = max(latest.get(k, 0.0), ts)
            except Exception:
                continue
        return latest
    except Exception:
        return {}


def _record_fire(key: str) -> None:
    _ensure_dir()
    try:
        with _STATE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "ts": int(time.time())}) + "\n")
    except Exception as exc:
        logger.debug("ops_alerts state write swallowed: %s", exc)


def _cooldown_active(key: str, kind: str) -> bool:
    """True if this alert key fired recently enough to skip."""
    cooldown_s = _COOLDOWN.get(kind, 3600)
    last = _read_state().get(key, 0.0)
    return (time.time() - last) < cooldown_s


def _ntfy(title: str, message: str, priority: str = "high", tags: list[str] | None = None) -> None:
    """Schedule ntfy push from any context (async or sync). Best-effort."""
    try:
        import asyncio

        from app.integrations import ntfy as _ntfy_mod

        async def _do() -> None:
            await _ntfy_mod.push(title, message, priority=priority, tags=tags or [])

        try:
            asyncio.get_running_loop().create_task(_do())
        except RuntimeError:
            # No running loop — fire synchronously
            try:
                asyncio.run(_do())
            except Exception:
                pass
    except Exception as exc:
        logger.debug("ops_alerts ntfy swallowed: %s", exc)


def alert_staff_failure(job: str, detail: str = "") -> dict[str, Any]:
    """W1.14: ek staff job crash (result ki jagah error return) — ops ko page karo
    (OPS_ALERTS-gated + per-job cooldown'd). Pehle failure sirf {"error"} me silent tha."""
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    key = f"staff_fail:{job}"
    if _cooldown_active(key, "staff_fail"):
        return {"alerted": False, "reason": "cooldown"}
    _ntfy(
        f"⚠️ staff job '{job}' failed",
        (f"'{job}' returned an error: {detail}")[:480],
        priority="high",
        tags=["warning", "staff"],
    )
    _record_fire(key)
    return {"alerted": True}


def alert_voice_circuit_breaker(reason: str = "") -> dict[str, Any]:
    """Voice controlled-calling circuit breaker tripped (provider-failure spike /
    compliance-unavailable / recording-unhealthy) — campaign auto-paused. Pages ops
    via ntfy (OPS_ALERTS-gated + cooldown'd so a sustained outage doesn't spam)."""
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    key = "voice_circuit_breaker"
    if _cooldown_active(key, "voice_circuit_breaker"):
        return {"alerted": False, "reason": "cooldown"}
    _ntfy(
        "\U0001f6d1 voice campaign PAUSED — circuit breaker",
        (f"Controlled calling auto-paused: {reason}")[:480],
        priority="high",
        tags=["stop_sign", "voice"],
    )
    _record_fire(key)
    return {"alerted": True}


def alert_paid_customer_stuck(client_id: str, business_name: str, reason: str) -> dict[str, Any]:
    """The jiya-makeover-class bug, closed: a PAID customer's value-delivery got
    stuck (WhatsApp send failed, no phone on file, AUTO_DELIVER_VALUE off, etc.)
    and — until this — the only trace was a jsonl line + a log WARNING nobody
    was watching. This pages the founder's phone directly via ntfy, same as
    every other real page in this module. OPS_ALERTS-gated + per-client
    cooldown'd (won't spam every scheduler tick while the same customer stays
    stuck) — but WILL re-fire every 3h until the underlying cause is fixed, by
    design (a paid customer left undelivered is not a one-time nudge).
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    key = f"paid_customer_stuck:{client_id}"
    if _cooldown_active(key, "paid_customer_stuck"):
        return {"alerted": False, "reason": "cooldown"}
    _ntfy(
        f"\U0001f6a8 PAID customer undelivered: {business_name or client_id}",
        (
            f"client={client_id} reason={reason} \u2014 this customer PAID and has not "
            f"received their value yet. Check /app/clients delivery panel now."
        )[:480],
        priority="urgent",
        tags=["rotating_light", "money"],
    )
    _record_fire(key)
    return {"alerted": True}


def alert_warm_sla(stuck: int, warm: int) -> dict[str, Any]:
    """W4.1: warm/stuck leads SLA nudge — FOUNDER ko ntfy (cooldown'd). Caller (office_hq)
    WARM_SLA_NUDGE se gate karta; yahan sirf cooldown + send. Founder-only, koi customer send NAHI.
    """
    key = "warm_sla_nudge"
    if _cooldown_active(key, "warm_sla"):
        return {"alerted": False, "reason": "cooldown"}
    _ntfy(
        f"⏰ {stuck} leads pending >SLA · {warm} warm",
        f"Hot Queue /app/inbox: {stuck} stuck (>24h) + {warm} warm (40-69) — aaj action lo.",
        priority="default",
        tags=["hourglass_flowing_sand", "leads"],
    )
    _record_fire(key)
    return {"alerted": True}


# --------------------------------------------------------------------------- #
# Alert 0 — ComplianceGate kill-switch active (legal liability) [D-1 / P0-3]
# --------------------------------------------------------------------------- #
def alert_compliance_disabled(detail: str = "") -> dict[str, Any]:
    """Page ops when COMPLIANCE_ENABLED=0 lets a call bypass the TCCCPR/TRAI gate
    (DND + calling-window + DLT) — a legal liability that must never be silent.
    Cooldown'd so a call-storm can't spam the channel. OPS_ALERTS-gated +
    never raises (the loud per-call log in compliance.py is the always-on path)."""
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    key = "compliance_disabled"
    if _cooldown_active(key, "compliance_disabled"):
        return {"alerted": False, "reason": "cooldown"}
    title = "🚨 ComplianceGate DISABLED (legal liability)"
    body = (
        "COMPLIANCE_ENABLED=0 — outbound calls are BYPASSING the TCCCPR/TRAI gate "
        "(DND / calling-window / DLT). Re-arm immediately by unsetting "
        "COMPLIANCE_ENABLED. " + (detail or "")
    )[:480]
    _ntfy(title, body, priority="urgent", tags=["rotating_light", "compliance"])
    _record_fire(key)
    return {"alerted": True}


# --------------------------------------------------------------------------- #
# Alert 1 — engineer-agent low score
# --------------------------------------------------------------------------- #
def maybe_alert_engineer_score(role: str, score: float | None, summary: str = "") -> dict[str, Any]:
    """Push ntfy when an engineer agent's score drops below threshold.

    Returns a small {"alerted": bool, "reason": ...} dict so the caller can
    log it. Never raises.
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    if score is None:
        return {"alerted": False, "reason": "no_score"}
    if float(score) >= _ENG_THRESHOLD:
        return {"alerted": False, "reason": "above_threshold", "score": float(score)}
    key = f"engineer_score:{role}"
    if _cooldown_active(key, "engineer_score"):
        return {"alerted": False, "reason": "cooldown", "score": float(score)}
    title = f"🔧 {role.upper()} score {score:.0f}/100"
    body = (summary or f"{role} engineer agent below {_ENG_THRESHOLD:.0f} threshold")[:480]
    _ntfy(title, body, priority="high", tags=["warning", role])
    _record_fire(key)
    return {"alerted": True, "score": float(score), "threshold": _ENG_THRESHOLD}


# --------------------------------------------------------------------------- #
# Alert 2 — eval_gate burst of rejects
# --------------------------------------------------------------------------- #
def maybe_alert_eval_reject(suite: str, metric: str, verdict: dict[str, Any]) -> dict[str, Any]:
    """When eval_gate rejects, check if there's a BURST of recent rejects for
    (suite, metric) and push ntfy on threshold. A single isolated reject is
    not pageable — three within the window is.
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    if (verdict or {}).get("decision") != "reject":
        return {"alerted": False, "reason": "not_reject"}

    # Count recent rejects for the same (suite, metric). We re-use eval_gate's
    # history file directly to avoid a second source of truth.
    try:
        from app.agents import eval_gate as _eg

        rows = _eg._read_history(limit=2000)
    except Exception:
        rows = []

    cutoff = time.time() - _EVAL_REJECT_WINDOW_SEC
    recent_rejects = 0
    for r in rows:
        if (r.get("suite") != suite) or (r.get("metric") != metric):
            continue
        if float(r.get("ts", 0) or 0) < cutoff:
            continue
        ext = r.get("extra") if isinstance(r.get("extra"), dict) else {}
        if (ext or {}).get("decision") == "reject":
            recent_rejects += 1

    if recent_rejects < _EVAL_REJECT_BURST:
        return {"alerted": False, "reason": "below_burst", "recent_rejects": recent_rejects}

    key = f"eval_reject:{suite}:{metric}"
    if _cooldown_active(key, "eval_reject"):
        return {"alerted": False, "reason": "cooldown", "recent_rejects": recent_rejects}
    title = f"🚨 eval_gate burst: {suite}/{metric}"
    body = (
        f"{recent_rejects} rejects in last {_EVAL_REJECT_WINDOW_SEC // 3600}h "
        f"(current={verdict.get('current'):.2f} vs baseline={verdict.get('baseline'):.2f})"
    )
    _ntfy(title, body, priority="urgent", tags=["rotating_light", "eval"])
    _record_fire(key)
    return {"alerted": True, "recent_rejects": recent_rejects}


# --------------------------------------------------------------------------- #
# Alert 3 — daily activation-readiness digest
# --------------------------------------------------------------------------- #
def daily_readiness_digest() -> dict[str, Any]:
    """Run activation-readiness probes; ntfy if any BLOCKER is present.

    Quiet by design — green days produce nothing on the phone. Only the first
    blocker-day in 20h triggers a push, so a stuck blocker doesn't re-page.
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    try:
        from app.api import activation as _ax

        items = [p() for p in _ax._PROBES]
    except Exception as exc:
        logger.debug("daily_readiness_digest probe error swallowed: %s", exc)
        return {"alerted": False, "reason": "probe_error"}

    blockers = [it for it in items if it.get("status") == "BLOCKER"]
    if not blockers:
        return {"alerted": False, "reason": "no_blockers", "items_checked": len(items)}

    key = "readiness_digest:any"
    if _cooldown_active(key, "readiness_digest"):
        return {"alerted": False, "reason": "cooldown", "blockers": len(blockers)}

    title = f"⚠️ Activation blockers: {len(blockers)}"
    lines = []
    for it in blockers[:5]:
        lines.append(f"- {it['label']}: {it.get('action', '')[:80]}")
    body = "\n".join(lines)[:1500]
    _ntfy(title, body, priority="default", tags=["warning", "activation"])
    _record_fire(key)
    return {"alerted": True, "blockers": len(blockers)}


# --------------------------------------------------------------------------- #
# Alert 4 — webhook dead-letter (L.3)
# --------------------------------------------------------------------------- #
_DEAD_LETTER_THRESHOLD = int(os.environ.get("OPS_ALERT_WEBHOOK_DEAD_LETTER_THRESHOLD", "3"))


def maybe_alert_webhook_dead_letter(webhook_id: str, client_id: str, url: str) -> dict[str, Any]:
    """Push ntfy when a webhook has accumulated N consecutive failures.

    Wired into customer_webhooks._deliver_one() after a non-2xx response so
    the customer (via the platform's own dashboard) sees a dead-letter
    marker, and the ops team gets paged.
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    try:
        from app.platform import customer_webhooks as _cw

        n = _cw.consecutive_failure_count(webhook_id)
    except Exception as exc:
        logger.debug("dead-letter probe error: %s", exc)
        return {"alerted": False, "reason": "probe_error"}

    if n < _DEAD_LETTER_THRESHOLD:
        return {"alerted": False, "reason": "below_threshold", "consecutive_failures": n}

    key = f"webhook_dead_letter:{webhook_id}"
    if _cooldown_active(key, "webhook_dead_letter"):
        return {"alerted": False, "reason": "cooldown", "consecutive_failures": n}

    title = f"🚨 Webhook dead-letter ({n} consecutive fails)"
    body = (
        f"client={client_id} url={url} — last {n} deliveries failed. "
        f"Likely the customer's endpoint is down or rejecting our signature."
    )[:1500]
    _ntfy(title, body, priority="urgent", tags=["rotating_light", "webhook"])
    _record_fire(key)
    return {"alerted": True, "consecutive_failures": n}


# --------------------------------------------------------------------------- #
# Alert 5 — payment failed (revenue signal)
# --------------------------------------------------------------------------- #
def maybe_alert_payment_failed(detail: str = "") -> dict[str, Any]:
    """Push ntfy when a payment attempt fails (gateway error, declined card,
    UPI verification failure, dunning charge bounce).

    Cooldown'd so a retry-storm on a single failing card can't spam the channel.
    OPS_ALERTS-gated + never raises (the call-site's own log is the always-on
    path). The call-site is wired by the billing/payment task.
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    key = "payment_failed"
    if _cooldown_active(key, "payment_failed"):
        return {"alerted": False, "reason": "cooldown"}
    title = "💳 Payment failed"
    body = ("A payment attempt failed — check the billing logs. " + (detail or ""))[:480]
    _ntfy(title, body, priority="high", tags=["credit_card", "billing"])
    _record_fire(key)
    return {"alerted": True}


# --------------------------------------------------------------------------- #
# Alert 6 — SMTP account disabled / email outreach blocked
# --------------------------------------------------------------------------- #
def maybe_alert_smtp_disabled(detail: str = "") -> dict[str, Any]:
    """Push ntfy when the SMTP account is disabled (e.g. Hostinger 554
    "Disabled by user") — every automated/outreach email is now blocked, a
    silent revenue/deliverability killer.

    Cooldown'd so a send-burst against the dead account can't spam the channel.
    OPS_ALERTS-gated + never raises (email_sender's own log/re-raise is the
    always-on path; this alert only sits beside it).
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    key = "smtp_disabled"
    if _cooldown_active(key, "smtp_disabled"):
        return {"alerted": False, "reason": "cooldown"}
    title = "📭 SMTP disabled / email outreach blocked"
    body = (
        "The SMTP account looks disabled — outbound email (alerts, outreach, "
        "followups) is BLOCKED. Check the mailbox / provider. " + (detail or "")
    )[:480]
    _ntfy(title, body, priority="urgent", tags=["no_entry", "email"])
    _record_fire(key)
    return {"alerted": True}


# --------------------------------------------------------------------------- #
# Alert 7 — UPI auto-activated (spot-check nudge, not a failure signal)
# --------------------------------------------------------------------------- #
def maybe_alert_upi_auto_activated(
    payment_id: str, client_id: str, plan: str, amount: float
) -> dict[str, Any]:
    """Push a low-priority ntfy heads-up whenever UPI_AUTO_ACTIVATE instantly
    activates a plan on a self-reported (unverified) payment claim, so a fake
    claim gets a real founder glance instead of silently disappearing into a
    JSONL file no one reads. Keyed per payment_id (not a shared key) — this is
    NOT a failure/spam scenario like the other alerts, every distinct payment
    should get its own nudge, so no cross-payment cooldown suppression.
    OPS_ALERTS-gated + never raises; a missed/failed push never blocks or
    delays the activation that already happened.
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    key = f"upi_auto_activated:{payment_id}"
    if _cooldown_active(key, "upi_auto_activated"):
        return {"alerted": False, "reason": "cooldown"}
    title = "⚡ UPI auto-activated — spot-check"
    body = (
        f"client={client_id} plan={plan} amount=₹{amount} auto-activated instantly "
        f"(self-reported UPI ref, no bank verification). Glance at it when convenient."
    )[:480]
    _ntfy(title, body, priority="default", tags=["zap", "billing"])
    _record_fire(key)
    return {"alerted": True}


__all__ = [
    "enabled",
    "maybe_alert_engineer_score",
    "maybe_alert_eval_reject",
    "maybe_alert_webhook_dead_letter",
    "maybe_alert_payment_failed",
    "maybe_alert_smtp_disabled",
    "daily_readiness_digest",
]
