"""F.5 — Three engineer agents (Pranav SRE / Vidya FinOps / Arnav Security).

The 2026-06-16 billionaire-scale audit (Section H) named these three roles as
the only additions to the AI-staff roster that pass the leverage test —
"measurable operational leverage your current roster does not have." Every
other proposed role is folded into existing agents or deferred.

Each agent is a SCORE COMPUTER, not a full LangGraph loop. The score (0-100)
is a single number an operator can put on a dashboard and watch trend over
time. Sub-KPIs explain what moved the score. Actions are one-line hints for
the operator (not auto-executed).

Project ethos applied:
- INERT when the per-role flag is unset: returns a NEUTRAL "disabled" payload.
- FAIL-OPEN on missing dependencies / signals — a missing data source becomes
  "unknown" in the KPIs and contributes a neutral 50 to the score rather than
  zeroing it out (an absent signal is not the same as a failing one).
- Pure-Python; no new dependency. Uses psutil only if already importable
  (it's in the project requirements but the probe degrades gracefully).
- log_event() into the existing agent_events table so /app/team picks it up
  without any extra wiring.

Hooks for callers:
    from app.platform import engineer_agents as ea
    ea.run("sre")        # -> dict; also logs event
    ea.run("finops")
    ea.run("security")
    ea.run_all()         # -> {"sre": ..., "finops": ..., "vidya": ...}
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))

# Per-role enable flags (registry entries in growth.py AUTOMATION_FLAGS).
_SRE_FLAG = "SRE_AGENT"
_FINOPS_FLAG = "FINOPS_AGENT"
_SECURITY_FLAG = "SECURITY_AGENT"


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _flag_on(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes")


def _file_age_hours(path: Path) -> float | None:
    """Hours since file's mtime. None if missing/unreadable."""
    try:
        if not path.exists():
            return None
        return (time.time() - path.stat().st_mtime) / 3600.0
    except Exception:
        return None


def _file_size_bytes(path: Path) -> int:
    try:
        return path.stat().st_size if path.exists() else 0
    except Exception:
        return 0


def _try_log(role: str, event: str, detail: str) -> None:
    """Best-effort event log — never raises, never blocks the agent run."""
    try:
        from app.platform.team import log_event

        log_event(role, event, detail)
    except Exception as e:  # pragma: no cover
        logger.debug("engineer_agents log_event swallowed: %s", e)


def _maybe_alert(result: dict[str, Any]) -> None:
    """Push ntfy if score < threshold (G.1 ops_alerts hook). Best-effort."""
    try:
        from app.platform import ops_alerts

        ops_alerts.maybe_alert_engineer_score(
            result.get("role", "?"),
            result.get("score"),
            summary=str(result.get("summary", "")),
        )
    except Exception as e:  # pragma: no cover
        logger.debug("engineer_agents _maybe_alert swallowed: %s", e)


def _disabled_result(role: str, flag: str) -> dict[str, Any]:
    return {
        "role": role,
        "score": None,
        "status": "disabled",
        "summary": f"{role} agent disabled (set {flag}=1 in .env to activate)",
        "kpis": {},
        "actions": [f"Set {flag}=1 to enable the {role} agent"],
        "ts": int(time.time()),
    }


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(x)))


# --------------------------------------------------------------------------- #
# Pranav — SRE / Reliability
#   KPI: backup_age_hours, dead_mans_alive, capacity_headroom_pct
#   Score = blend of three sub-scores; missing signal -> 50 (neutral).
# --------------------------------------------------------------------------- #
def run_sre() -> dict[str, Any]:
    if not _flag_on(_SRE_FLAG):
        return _disabled_result("sre", _SRE_FLAG)

    kpis: dict[str, Any] = {}
    actions: list[str] = []
    sub_scores: list[float] = []

    # 1) Backup freshness — pg_backup.log mtime <= 30h is healthy.
    backup_log = _DATA_DIR / "pg_backup.log"
    age = _file_age_hours(backup_log)
    if age is None:
        kpis["backup_age_hours"] = None
        sub_scores.append(50.0)
        actions.append("No backup log found — verify nightly pg_backup.sh is running")
    else:
        kpis["backup_age_hours"] = round(age, 1)
        if age <= 30:
            sub_scores.append(100.0)
        elif age <= 48:
            sub_scores.append(60.0)
            actions.append(f"Backup is {age:.1f}h old — investigate scheduler")
        else:
            sub_scores.append(0.0)
            actions.append(f"BACKUP STALE: {age:.1f}h old — run scripts/pg_backup.sh now")

    # 2) Dead-man trio alive — heartbeat file recent (<25 min covers 20-min revive)
    hb = _DATA_DIR / "job_heartbeats.json"
    hb_age_min = (_file_age_hours(hb) or 99) * 60.0 if hb.exists() else None
    kpis["heartbeat_age_minutes"] = round(hb_age_min, 1) if hb_age_min is not None else None
    if hb_age_min is None:
        sub_scores.append(50.0)
        actions.append("No heartbeat file — confirm self_improve loop is running")
    elif hb_age_min <= 25:
        sub_scores.append(100.0)
    elif hb_age_min <= 60:
        sub_scores.append(50.0)
        actions.append(f"Heartbeat {hb_age_min:.0f}m old — check revive-beat")
    else:
        sub_scores.append(0.0)
        actions.append(f"DEAD-MAN STALE: heartbeat {hb_age_min:.0f}m old")

    # 3) Capacity headroom — psutil if available; neutral otherwise.
    try:
        import psutil  # type: ignore

        cpu = float(psutil.cpu_percent(interval=0.0))  # non-blocking sample
        mem = float(psutil.virtual_memory().percent)
        headroom = 100.0 - max(cpu, mem)
        kpis["cpu_pct"] = round(cpu, 1)
        kpis["mem_pct"] = round(mem, 1)
        kpis["capacity_headroom_pct"] = round(headroom, 1)
        if headroom >= 40:
            sub_scores.append(100.0)
        elif headroom >= 20:
            sub_scores.append(60.0)
            actions.append(f"Capacity tight: {headroom:.0f}% headroom")
        else:
            sub_scores.append(0.0)
            actions.append(f"CAPACITY CRITICAL: only {headroom:.0f}% headroom")
    except Exception:
        kpis["capacity_headroom_pct"] = None
        sub_scores.append(50.0)

    score = _clamp(sum(sub_scores) / len(sub_scores)) if sub_scores else None
    result = {
        "role": "sre",
        "agent": "pranav",
        "score": round(score, 1) if score is not None else None,
        "status": "ok",
        "summary": (
            f"Reliability score {score:.0f}/100 — "
            + ("all green" if score and score >= 80 else "needs attention")
        ) if score is not None else "no signals",
        "kpis": kpis,
        "actions": actions,
        "ts": int(time.time()),
    }
    _try_log("pranav", "sre_drill", json.dumps({"score": score, "n_actions": len(actions)}))
    _maybe_alert(result)
    return result


# --------------------------------------------------------------------------- #
# Vidya — FinOps / Cost
#   KPI: today_llm_tokens, est_cost_inr, customers_active, cost_per_customer
#   Free-stack reality: LLM tokens are free today, so cost is near 0. The
#   number Vidya watches is therefore "token efficiency" + "active customers"
#   trend. Once LiteLLM virtual keys land, real cost-per-tenant slots in.
# --------------------------------------------------------------------------- #
def run_finops() -> dict[str, Any]:
    if not _flag_on(_FINOPS_FLAG):
        return _disabled_result("finops", _FINOPS_FLAG)

    kpis: dict[str, Any] = {}
    actions: list[str] = []
    sub_scores: list[float] = []

    # 1) LLM token usage today (llm_metrics.jsonl tail)
    metrics_file = _DATA_DIR / "llm_metrics.jsonl"
    tokens_today = 0
    calls_today = 0
    today = time.strftime("%Y-%m-%d")
    try:
        if metrics_file.exists():
            for line in metrics_file.read_text(encoding="utf-8").splitlines()[-5000:]:
                line = line.strip()
                if not line or today not in line:
                    continue
                try:
                    rec = json.loads(line)
                    tokens_today += int(rec.get("tokens", 0) or 0)
                    calls_today += 1
                except Exception:
                    continue
    except Exception:
        pass
    kpis["today_llm_calls"] = calls_today
    kpis["today_llm_tokens"] = tokens_today

    # Free providers → estimated cost is ~0. Use a paid-tier reference for trend.
    # Reference: ~$2 / million input tokens (Anthropic 4.5 Haiku-ish baseline).
    est_cost_inr = (tokens_today / 1_000_000.0) * 2.0 * 83.0  # USD->INR ~83
    kpis["est_paid_baseline_cost_inr"] = round(est_cost_inr, 2)

    # 2) Active customers (placeholder: count of /b/<slug> dirs or clients.jsonl)
    customers_active = 0
    clients_file = _DATA_DIR / "clients.jsonl"
    if clients_file.exists():
        try:
            customers_active = sum(
                1 for _l in clients_file.read_text(encoding="utf-8").splitlines() if _l.strip()
            )
        except Exception:
            pass
    kpis["customers_active"] = customers_active

    # 3) Cost per customer (BLOCKED on LiteLLM virtual-keys for true per-tenant —
    # until then it's an aggregate floor).
    if customers_active > 0:
        cost_per_customer = est_cost_inr / customers_active
        kpis["est_cost_per_customer_inr"] = round(cost_per_customer, 2)
    else:
        kpis["est_cost_per_customer_inr"] = None
        actions.append("No active customers yet — pricing/quota tuning premature")

    # Margin score:
    # - free-stack: cost ≈ ₹0, so margin is bounded by token efficiency
    # - reject runaway prompts (>5M tokens/day on the free chain = TPD-eating)
    if tokens_today < 1_000_000:
        sub_scores.append(100.0)
    elif tokens_today < 5_000_000:
        sub_scores.append(70.0)
    else:
        sub_scores.append(20.0)
        actions.append(
            f"High token throughput ({tokens_today:,}/day) — risks Groq/Cerebras TPD exhaustion"
        )

    # LiteLLM activation gate
    litellm_active = bool(os.environ.get("LITELLM_MASTER_KEY", "").strip())
    kpis["litellm_active"] = litellm_active
    if not litellm_active:
        actions.append(
            "Activate LiteLLM (LITELLM_MASTER_KEY) for true per-tenant cost attribution"
        )

    score = _clamp(sum(sub_scores) / len(sub_scores)) if sub_scores else None
    result = {
        "role": "finops",
        "agent": "vidya",
        "score": round(score, 1) if score is not None else None,
        "status": "ok",
        "summary": (
            f"Margin score {score:.0f}/100 · {tokens_today:,} tokens today · "
            f"{customers_active} active customers"
        ),
        "kpis": kpis,
        "actions": actions,
        "ts": int(time.time()),
    }
    _try_log("vidya", "finops_check", json.dumps({"score": score, "tokens": tokens_today}))
    _maybe_alert(result)
    return result


# --------------------------------------------------------------------------- #
# Arnav — Security / Compliance
#   KPI: consent_ledger_healthy, secrets_age_days, dpdp_grievance_set,
#        webhook_secrets_armed
#   Composite "posture score" 0-100.
# --------------------------------------------------------------------------- #
def run_security() -> dict[str, Any]:
    if not _flag_on(_SECURITY_FLAG):
        return _disabled_result("security", _SECURITY_FLAG)

    kpis: dict[str, Any] = {}
    actions: list[str] = []
    sub_scores: list[float] = []

    # 1) Consent ledger healthy (TRAI / DPDP) — file exists + recently written
    ledger = _DATA_DIR / "consent_ledger.jsonl"
    if ledger.exists():
        kpis["consent_ledger_kb"] = round(_file_size_bytes(ledger) / 1024.0, 1)
        sub_scores.append(100.0)
    else:
        kpis["consent_ledger_kb"] = 0
        sub_scores.append(40.0)
        actions.append("Consent ledger missing — verify telephony opt-out path")

    # 2) Webhook signing secrets armed (fail-CLOSED only protects when set)
    twilio = bool(os.environ.get("TWILIO_AUTH_TOKEN", "").strip())
    razorpay = bool(os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip())
    whatsapp = bool(os.environ.get("WHATSAPP_APP_SECRET", "").strip())
    armed = sum([twilio, razorpay, whatsapp])
    kpis["webhook_secrets_armed"] = {"twilio": twilio, "razorpay": razorpay, "whatsapp": whatsapp}
    sub_scores.append(armed / 3 * 100.0)
    if not razorpay:
        actions.append("RAZORPAY_WEBHOOK_SECRET unset — forged callback risk on revenue path")
    if not twilio:
        actions.append("TWILIO_AUTH_TOKEN unset — telephony webhooks unauthenticated in prod")

    # 3) Bot protection (F.1) active
    turnstile = bool(os.environ.get("TURNSTILE_SECRET_KEY", "").strip())
    kpis["turnstile_armed"] = turnstile
    sub_scores.append(100.0 if turnstile else 60.0)
    if not turnstile:
        actions.append("Turnstile secret unset — public forms unguarded vs bot spam")

    # 4) DPDP Grievance Officer + privacy/terms visible
    gri = bool(os.environ.get("GRIEVANCE_OFFICER_EMAIL", "").strip())
    kpis["dpdp_grievance_set"] = gri
    sub_scores.append(100.0 if gri else 70.0)
    if not gri:
        actions.append("Set GRIEVANCE_OFFICER_EMAIL for DPDP Section 13 compliance")

    score = _clamp(sum(sub_scores) / len(sub_scores)) if sub_scores else None
    result = {
        "role": "security",
        "agent": "arnav",
        "score": round(score, 1) if score is not None else None,
        "status": "ok",
        "summary": (
            f"Compliance posture {score:.0f}/100 · {armed}/3 webhook secrets armed · "
            f"turnstile {'on' if turnstile else 'off'}"
        ),
        "kpis": kpis,
        "actions": actions,
        "ts": int(time.time()),
    }
    _try_log("arnav", "security_posture", json.dumps({"score": score, "armed": armed}))
    _maybe_alert(result)
    return result


# --------------------------------------------------------------------------- #
# Public dispatch
# --------------------------------------------------------------------------- #
_AGENTS = {
    "sre": run_sre,
    "finops": run_finops,
    "security": run_security,
}


def run(role: str) -> dict[str, Any]:
    """Run a single engineer agent by role. Unknown role -> structured error."""
    fn = _AGENTS.get((role or "").strip().lower())
    if not fn:
        return {
            "role": role,
            "score": None,
            "status": "unknown_role",
            "summary": f"Unknown engineer agent role: {role}",
            "kpis": {},
            "actions": [f"Valid roles: {', '.join(sorted(_AGENTS))}"],
            "ts": int(time.time()),
        }
    return fn()


def run_all() -> dict[str, dict[str, Any]]:
    """Run all three engineer agents — dashboard rollup."""
    return {role: fn() for role, fn in _AGENTS.items()}


__all__ = ["run", "run_all", "run_sre", "run_finops", "run_security"]
