"""Email warmup ramp + bounce auto-pause — sender-reputation guard (Smartlead/Instantly pattern, free).

Research (June 2026): naya domain/inbox ramp = wk1 3-10/day -> wk2 10-25 -> wk3 25-35
-> wk4+ 35-50; Google bounce hard-ceiling 2%, industry auto-pause trigger = 1.8%.
Humara static cap 25/day conservative tha, par: (a) ramp nahi (naya inbox bhi day-1
se 25 bhejta), (b) bounce-spike pe auto-pause nahi (sender-rep burn risk).

Design (self-contained, jsonl-free single JSON state `data/email_warmup.json`):
  - GATED `EMAIL_WARMUP=1` (default OFF => effective_cap(base) == base, zero change).
  - Start-marker pehli gated call pe auto-set (ya `WARMUP_START_DATE=YYYY-MM-DD` env).
  - Ramp: wk1 5/day, wk2 15, wk3 25, wk4+ base (conservative edge of research).
  - record_sent()/record_bounce() -> rolling 7-din counters; rate >= BOUNCE_PAUSE_PCT
    (1.8%) aur sends >= 20 => 24h auto-pause + NOTIFY_EMAIL alert (best-effort).
  - Wired: auto_outreach dono cap-spots (defensive try/except, fallback = base cap).
Kabhi raise nahi karta.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STATE = os.path.join("data", "email_warmup.json")

BOUNCE_PAUSE_PCT = 1.8  # Smartlead/Instantly auto-pause trigger
# Spam-complaint rate = #1 2026 Gmail/Yahoo deliverability gate. Google "Spammy"
# threshold 0.30% (hard), 0.10% = ideal ceiling. Auto-pause buffer = 0.25% (pause
# BEFORE Google flags the domain — recovery is slow/expensive once flagged).
# ⚠️ This threshold measures USER-REPORTED SPAM ("Report Spam" → Postmaster Tools) ONLY.
# Unsubscribes are NOT complaints — see UNSUB_PAUSE_PCT below + ADR-103.
COMPLAINT_PAUSE_PCT = 0.25
# Unsubscribe = the OPPOSITE signal to a spam report. Gmail's 2024 bulk-sender rules
# MANDATE one-click list-unsubscribe and reward making it easy; 0.2-2% unsub on cold
# outreach is normal/healthy. So unsubs get their own bucket + a much higher ceiling
# that only trips on a genuinely mistargeted list (ADR-103: conflating the two kept
# the primary GTM channel paused for 3 days on 5 healthy unsubs).
UNSUB_PAUSE_PCT = 2.0
PAUSE_HOURS = 24
_MIN_SENDS_FOR_RATE = 20  # chhote sample pe pause mat karo (1 bounce / 5 sends != crisis)
# Complaint sample bigger — 0.25% of <400 sends = <1 complaint, so rate noisy at low N.
_MIN_SENDS_FOR_COMPLAINT_RATE = 100
_MIN_SENDS_FOR_UNSUB_RATE = 100
# (week_index_from_1, cap) — wk4+ = base cap (caller ka).
_RAMP = {1: 5, 2: 15, 3: 25}


def _is_unsub_reason(reason: str) -> bool:
    """True = recipient opted out (healthy). False = real spam report / unknown.

    Callers today: email_unsub.suppress -> "unsub_<reason>", reply_agent -> "reply_unsubscribe".
    Unknown/blank reasons stay on the CONSERVATIVE side (treated as a complaint) so a
    future real FBL feed is gated correctly by default.
    """
    r = (reason or "").strip().lower()
    return r.startswith("unsub") or "unsubscribe" in r


def _enabled() -> bool:
    return os.environ.get("EMAIL_WARMUP", "0").strip().lower() in ("1", "true", "yes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> dict[str, Any]:
    try:
        if os.path.exists(_STATE):
            with open(_STATE, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save(state: dict[str, Any], _already_locked: bool = False) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE) or ".", exist_ok=True)
        payload = json.dumps(state, ensure_ascii=False, default=str)
        if _already_locked:
            # Caller already holds file_lock(_STATE); locked_rewrite would self-block on
            # the per-open-description flock. Write atomically (tmp+os.replace) directly.
            tmp = f"{_STATE}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, _STATE)
            return
        from app.utils.file_lock import locked_rewrite

        if not locked_rewrite(_STATE, payload):
            with open(_STATE, "w", encoding="utf-8") as f:
                f.write(payload)
    except Exception as e:
        logger.debug(f"[warmup] save skipped: {e}")


def _start_date(state: dict[str, Any]) -> date:
    """Warmup start: env override > stored marker > aaj (auto-set)."""
    env = os.environ.get("WARMUP_START_DATE", "").strip()
    if env:
        try:
            return date.fromisoformat(env)
        except Exception:
            pass
    raw = str(state.get("start_date") or "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except Exception:
            pass
    today = _now().date()
    state["start_date"] = today.isoformat()
    _save(state)
    return today


def _trim_7d(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = (_now() - timedelta(days=7)).isoformat()
    return [e for e in events if str(e.get("at", "")) >= cutoff][-2000:]


def is_paused(state: dict[str, Any] | None = None) -> bool:
    st = state if state is not None else _load()
    raw = str(st.get("paused_until") or "")
    if not raw:
        return False
    try:
        until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return _now() < until
    except Exception:
        return False


def bounce_rate_7d(state: dict[str, Any] | None = None) -> tuple[float, int, int]:
    """(rate_pct, sent_7d, bounced_7d) rolling 7 din."""
    st = state if state is not None else _load()
    sent = sum(int(e.get("n") or 1) for e in _trim_7d(list(st.get("sent_events") or [])))
    bounced = len(_trim_7d(list(st.get("bounce_events") or [])))
    rate = (bounced / sent * 100.0) if sent > 0 else 0.0
    return round(rate, 2), sent, bounced


def complaint_rate_7d(state: dict[str, Any] | None = None) -> tuple[float, int, int]:
    """(rate_pct, sent_7d, complaints_7d) rolling 7 din — spam-complaint gate (<0.3%).

    Counts REAL spam reports only. Unsubscribes live in `unsub_events` (ADR-103).
    """
    st = state if state is not None else _load()
    sent = sum(int(e.get("n") or 1) for e in _trim_7d(list(st.get("sent_events") or [])))
    complaints = len(_trim_7d(list(st.get("complaint_events") or [])))
    rate = (complaints / sent * 100.0) if sent > 0 else 0.0
    return round(rate, 3), sent, complaints


def unsub_rate_7d(state: dict[str, Any] | None = None) -> tuple[float, int, int]:
    """(rate_pct, sent_7d, unsubs_7d) rolling 7 din — mistargeted-list gate (<2%)."""
    st = state if state is not None else _load()
    sent = sum(int(e.get("n") or 1) for e in _trim_7d(list(st.get("sent_events") or [])))
    unsubs = len(_trim_7d(list(st.get("unsub_events") or [])))
    rate = (unsubs / sent * 100.0) if sent > 0 else 0.0
    return round(rate, 3), sent, unsubs


def effective_cap(base_cap: int) -> int:
    """Outreach ka aaj ka cap. Flag OFF => base_cap as-is (zero behaviour change)."""
    try:
        base = max(0, int(base_cap))
        if not _enabled():
            return base
        st = _load()
        if is_paused(st):
            return 0
        days = max(0, (_now().date() - _start_date(st)).days)
        week = days // 7 + 1
        ramp = _RAMP.get(week)
        return min(base, ramp) if ramp is not None else base
    except Exception as e:
        logger.debug(f"[warmup] effective_cap fallback: {e}")
        return max(0, int(base_cap or 0))


def record_sent(n: int = 1) -> None:
    """Outreach run ke baad sends gin lo (flag-independent — stats hamesha)."""
    try:
        if int(n or 0) <= 0:
            return
        from app.utils.file_lock import file_lock

        # lock the whole load->modify->save so a concurrent record_bounce/complaint
        # (other worker process) can't clobber this appended sent event (lost update).
        with file_lock(_STATE):
            st = _load()
            events = _trim_7d(list(st.get("sent_events") or []))
            events.append({"at": _now().isoformat(), "n": int(n)})
            st["sent_events"] = events
            _save(st, _already_locked=True)
    except Exception:
        pass


def record_bounce(email: str = "", reason: str = "") -> dict[str, Any]:
    """Bounce report (manual/reply-agent) — threshold cross pe 24h auto-pause + alert."""
    out: dict[str, Any] = {"recorded": False, "paused": False}
    try:
        from app.utils.file_lock import file_lock

        with file_lock(
            _STATE
        ):  # lock load->modify->save (else concurrent writer drops this bounce event)
            st = _load()
            events = _trim_7d(list(st.get("bounce_events") or []))
            events.append(
                {
                    "at": _now().isoformat(),
                    "email": (email or "")[:120],
                    "reason": (reason or "")[:200],
                }
            )
            st["bounce_events"] = events
            out["recorded"] = True
            rate, sent, bounced = bounce_rate_7d(st)
            out.update({"rate_pct": rate, "sent_7d": sent, "bounced_7d": bounced})
            if sent >= _MIN_SENDS_FOR_RATE and rate >= BOUNCE_PAUSE_PCT and not is_paused(st):
                st["paused_until"] = (_now() + timedelta(hours=PAUSE_HOURS)).isoformat()
                st["paused_reason"] = (
                    f"bounce rate {rate}% >= {BOUNCE_PAUSE_PCT}% ({bounced}/{sent} in 7d)"
                )
                out["paused"] = True
                logger.warning(f"[warmup] AUTO-PAUSE: {st['paused_reason']}")
            _save(st, _already_locked=True)
        if out["paused"]:
            _alert(st.get("paused_reason", ""))
    except Exception as e:
        logger.debug(f"[warmup] record_bounce skipped: {e}")
    return out


def _record_negative_signal(
    *,
    bucket: str,
    email: str,
    reason: str,
    rate_fn: Any,
    threshold_pct: float,
    min_sends: int,
    count_key: str,
    label: str,
) -> dict[str, Any]:
    """Shared append -> rolling-rate -> maybe-pause path for complaints and unsubs."""
    out: dict[str, Any] = {"recorded": False, "paused": False}
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_STATE):  # lock load->modify->save (else concurrent writer drops this event)
            st = _load()
            events = _trim_7d(list(st.get(bucket) or []))
            events.append(
                {
                    "at": _now().isoformat(),
                    "email": (email or "")[:120],
                    "reason": (reason or "")[:200],
                }
            )
            st[bucket] = events
            out["recorded"] = True
            rate, sent, count = rate_fn(st)
            out.update({"rate_pct": rate, "sent_7d": sent, count_key: count})
            if sent >= min_sends and rate >= threshold_pct and not is_paused(st):
                st["paused_until"] = (_now() + timedelta(hours=PAUSE_HOURS)).isoformat()
                st["paused_reason"] = (
                    f"{label} rate {rate}% >= {threshold_pct}% ({count}/{sent} in 7d)"
                )
                out["paused"] = True
                logger.warning(f"[warmup] AUTO-PAUSE ({label}): {st['paused_reason']}")
            _save(st, _already_locked=True)
        if out["paused"]:
            _alert(st.get("paused_reason", ""))
    except Exception as e:
        logger.debug(f"[warmup] record {label} skipped: {e}")
    return out


def record_unsub(email: str = "", reason: str = "") -> dict[str, Any]:
    """Opt-out report — own bucket, own (much higher) ceiling. Never raises.

    An unsubscribe is a HEALTHY signal: Gmail's 2024 bulk-sender rules mandate one-click
    list-unsubscribe and reward easy opt-out. This gate exists only to catch a genuinely
    mistargeted list (>= UNSUB_PAUSE_PCT), NOT to police normal opt-out rates.

    NOTE: actual opt-out SUPPRESSION (DPDP / consent ledger, instant + cross-channel) is a
    separate code path (`email_unsub.suppress`) and is unaffected by this counter.
    """
    return _record_negative_signal(
        bucket="unsub_events",
        email=email,
        reason=reason,
        rate_fn=unsub_rate_7d,
        threshold_pct=UNSUB_PAUSE_PCT,
        min_sends=_MIN_SENDS_FOR_UNSUB_RATE,
        count_key="unsubs_7d",
        label="unsubscribe",
    )


def record_complaint(email: str = "", reason: str = "") -> dict[str, Any]:
    """Spam-complaint report — threshold cross pe 24h auto-pause + alert. Never raises.

    Spam-complaint rate = #1 2026 Gmail/Yahoo deliverability gate (must stay <0.3%; we
    auto-pause at the 0.25% buffer). This counts USER-REPORTED SPAM only.

    ADR-103: unsubscribe reasons are routed to `record_unsub` instead. Previously every
    caller was an unsubscribe, so this gate had never measured a single real complaint —
    it just paused the whole GTM channel whenever someone opted out. Routing here (rather
    than at the call sites) keeps both existing callers unchanged and means a future real
    FBL/spam-report feed lands on the correct — unweakened — 0.25% threshold.
    """
    if _is_unsub_reason(reason):
        return record_unsub(email, reason)
    return _record_negative_signal(
        bucket="complaint_events",
        email=email,
        reason=reason,
        rate_fn=complaint_rate_7d,
        threshold_pct=COMPLAINT_PAUSE_PCT,
        min_sends=_MIN_SENDS_FOR_COMPLAINT_RATE,
        count_key="complaints_7d",
        label="complaint",
    )


def _alert(reason: str) -> None:
    """NOTIFY_EMAIL ko pause-alert (best-effort, fire-and-forget)."""
    try:
        to = os.environ.get("NOTIFY_EMAIL", "").strip()
        if not to:
            return
        import asyncio

        from app.integrations.email_sender import email_sender

        async def _go() -> None:
            try:
                await email_sender.send_email(
                    [to],
                    "⚠️ Cold-email outreach AUTO-PAUSED",
                    f"Outreach {PAUSE_HOURS}h ke liye paused: {reason}\n\n"
                    f"Lists saaf karo (MX-verify on hai?), phir data/email_warmup.json me "
                    f"paused_until hatao ya wait karo. — LeadsGenAI warmup guard",
                )
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_go())
        except RuntimeError:
            asyncio.run(_go())
    except Exception:
        pass


def resume() -> bool:
    """Manual un-pause (admin API)."""
    try:
        st = _load()
        st.pop("paused_until", None)
        st.pop("paused_reason", None)
        _save(st)
        return True
    except Exception:
        return False


def status() -> dict[str, Any]:
    st = _load()
    rate, sent, bounced = bounce_rate_7d(st)
    c_rate, _c_sent, complaints = complaint_rate_7d(st)
    u_rate, _u_sent, unsubs = unsub_rate_7d(st)
    days = (
        max(0, (_now().date() - _start_date(st)).days)
        if st.get("start_date") or os.environ.get("WARMUP_START_DATE")
        else 0
    )
    week = days // 7 + 1
    return {
        "enabled": _enabled(),
        "start_date": st.get("start_date") or os.environ.get("WARMUP_START_DATE", ""),
        "day": days + 1,
        "week": week,
        "ramp_cap_this_week": _RAMP.get(week, "base"),
        "paused": is_paused(st),
        "paused_reason": st.get("paused_reason", ""),
        "bounce_rate_7d_pct": rate,
        "sent_7d": sent,
        "bounced_7d": bounced,
        "pause_threshold_pct": BOUNCE_PAUSE_PCT,
        "complaint_rate_7d_pct": c_rate,
        "complaints_7d": complaints,
        "complaint_pause_threshold_pct": COMPLAINT_PAUSE_PCT,
        "unsub_rate_7d_pct": u_rate,
        "unsubs_7d": unsubs,
        "unsub_pause_threshold_pct": UNSUB_PAUSE_PCT,
    }


__all__ = [
    "effective_cap",
    "record_sent",
    "record_bounce",
    "record_complaint",
    "record_unsub",
    "bounce_rate_7d",
    "complaint_rate_7d",
    "unsub_rate_7d",
    "is_paused",
    "resume",
    "status",
    "BOUNCE_PAUSE_PCT",
    "COMPLAINT_PAUSE_PCT",
    "UNSUB_PAUSE_PCT",
]
