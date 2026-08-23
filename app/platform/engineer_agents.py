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
# 2026-06-25 council-added engineer agents (genuinely-uncovered loops, not duplicates):
_DBRE_FLAG = "DBRE_AGENT"  # Kabir — Postgres reliability (slow-queries/indices/connections)
_DEPS_FLAG = "DEPS_AGENT"  # Aryan — dependency/supply-chain CVE audit (proposal-only)
_DATA_INTEGRITY_FLAG = "DATA_INTEGRITY_AGENT"  # Diya — lead/CRM data integrity (report-only)


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
            (
                f"Reliability score {score:.0f}/100 — "
                + ("all green" if score and score >= 80 else "needs attention")
            )
            if score is not None
            else "no signals"
        ),
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
        actions.append("Activate LiteLLM (LITELLM_MASTER_KEY) for true per-tenant cost attribution")

    # I.1: when LiteLLM data is available, REAL per-tenant cost replaces the
    # token-volume proxy. Flag margin-negative clients (spend > ₹0 + no client_id
    # mapping = "unmapped spend") as a concrete FinOps action.
    try:
        from app.platform import litellm_costs as _lc

        if _lc.enabled():
            spend = _lc.per_key_spend_sync(hours=24)
            if spend.get("available"):
                kpis["litellm_total_usd_24h"] = spend.get("total_usd")
                kpis["litellm_keys_tracked"] = len(spend.get("spend", []))
                # Unmapped spend = keys without a client_id in keymap (revenue leak risk)
                unmapped = [r for r in (spend.get("spend") or []) if not r.get("client_id")]
                if unmapped:
                    unmapped_usd = round(sum(r.get("spend_usd", 0.0) for r in unmapped), 4)
                    kpis["litellm_unmapped_spend_usd"] = unmapped_usd
                    if unmapped_usd > 0:
                        actions.append(
                            f"${unmapped_usd:.2f} of LLM spend has no client_id mapping "
                            f"(populate data/litellm_keymap.jsonl)"
                        )
    except Exception as exc:
        logger.debug("vidya litellm enrichment swallowed: %s", exc)

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
#
#   Scheduler path: run_security() gated by SECURITY_AGENT (legacy).
#   Agent Runtime path: compute_security_posture() after SECURITY_POSTURE_AGENT
#   adapter gate — never OR the two flags for eligibility.
# --------------------------------------------------------------------------- #
def compute_security_posture() -> dict[str, Any]:
    """Read-only posture score. No flag check — callers gate independently."""
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

    # 2) Webhook signing secrets armed (fail-CLOSED only protects when set).
    # Vobiz doesn't sign callbacks (no per-provider secret to arm) — WhatsApp is
    # the only externally-signed webhook since Twilio was removed 2026-07-07.
    whatsapp = bool(os.environ.get("WHATSAPP_APP_SECRET", "").strip())
    kpis["webhook_secrets_armed"] = {"whatsapp": whatsapp}
    sub_scores.append(100.0 if whatsapp else 0.0)

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
            f"Compliance posture {score:.0f}/100 · webhook secrets "
            f"{'armed' if whatsapp else 'unarmed'} · turnstile {'on' if turnstile else 'off'}"
        ),
        "kpis": kpis,
        "actions": actions,
        "ts": int(time.time()),
        "remediation_performed": False,
        "read_only": True,
    }
    _try_log("arnav", "security_posture", json.dumps({"score": score, "armed": whatsapp}))
    _maybe_alert(result)
    return result


def run_security() -> dict[str, Any]:
    """Scheduler / staff entry — gated by SECURITY_AGENT only."""
    if not _flag_on(_SECURITY_FLAG):
        return _disabled_result("security", _SECURITY_FLAG)
    return compute_security_posture()


# --------------------------------------------------------------------------- #
# Kabir — DB Reliability Engineer (council 2026-06-25)
#   Fills Pranav's blind spot: Pranav watches backup/heartbeat/capacity, NOT
#   Postgres query-health. As lead/call data scales, slow queries + unused/
#   bloating indices are the silent killer. STRICTLY read-only (pg catalog
#   views only); SQLite rollback-mode / unreachable DB -> neutral, never fails.
# --------------------------------------------------------------------------- #
def run_dbre() -> dict[str, Any]:
    if not _flag_on(_DBRE_FLAG):
        return _disabled_result("dbre", _DBRE_FLAG)

    kpis: dict[str, Any] = {}
    actions: list[str] = []
    sub_scores: list[float] = []

    try:
        from sqlalchemy import text

        from app.models.base import get_db_session

        with get_db_session() as db:
            try:
                dialect = db.get_bind().dialect.name
            except Exception:
                dialect = ""
            kpis["db_dialect"] = dialect or "unknown"

            if dialect != "postgresql":
                # SQLite rollback-backup mode (or unknown) — pg health N/A, not a failure.
                return {
                    "role": "dbre",
                    "agent": "kabir",
                    "score": None,
                    "status": "ok",
                    "summary": f"DB is '{dialect or 'unknown'}' not Postgres — pg health checks skipped",
                    "kpis": kpis,
                    "actions": ["pg reliability checks apply only to the Postgres prod DB"],
                    "ts": int(time.time()),
                }

            # 1) Active connections (PgBouncer fronts Postgres; watch backend count).
            try:
                conns = int(db.execute(text("SELECT count(*) FROM pg_stat_activity")).scalar() or 0)
                kpis["active_connections"] = conns
                if conns < 80:
                    sub_scores.append(100.0)
                elif conns < 150:
                    sub_scores.append(60.0)
                    actions.append(f"{conns} DB connections — watch PgBouncer pool sizing")
                else:
                    sub_scores.append(20.0)
                    actions.append(f"HIGH connection count ({conns}) — risk of pool exhaustion")
            except Exception:
                sub_scores.append(50.0)

            # 2) Unused indices (idx_scan=0) — write-amplification + bloat as data grows.
            try:
                unused = int(
                    db.execute(
                        text("SELECT count(*) FROM pg_stat_user_indexes WHERE idx_scan = 0")
                    ).scalar()
                    or 0
                )
                kpis["unused_indexes"] = unused
                if unused <= 5:
                    sub_scores.append(100.0)
                elif unused <= 20:
                    sub_scores.append(70.0)
                    actions.append(f"{unused} never-scanned indexes — review for DROP")
                else:
                    sub_scores.append(40.0)
                    actions.append(
                        f"{unused} unused indexes bloating writes — audit + DROP candidates"
                    )
            except Exception:
                sub_scores.append(50.0)

            # 3) Slow queries via pg_stat_statements (extension may be absent → neutral).
            try:
                slow = int(
                    db.execute(
                        text("SELECT count(*) FROM pg_stat_statements WHERE mean_exec_time > 1000")
                    ).scalar()
                    or 0
                )
                kpis["slow_queries_gt_1s"] = slow
                if slow == 0:
                    sub_scores.append(100.0)
                elif slow <= 5:
                    sub_scores.append(60.0)
                    actions.append(f"{slow} query patterns avg >1s — add indexes / optimize")
                else:
                    sub_scores.append(20.0)
                    actions.append(
                        f"{slow} slow query patterns (>1s avg) — investigate top offenders"
                    )
            except Exception:
                kpis["slow_queries_gt_1s"] = None
                actions.append(
                    "pg_stat_statements not enabled — CREATE EXTENSION for slow-query visibility"
                )

            # 4) DB size (informational trend).
            try:
                size = int(
                    db.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0
                )
                kpis["db_size_mb"] = round(size / (1024.0 * 1024.0), 1)
            except Exception:
                pass
    except Exception:
        # DB unconfigured / unreachable — fail-open neutral (absent != failing).
        return {
            "role": "dbre",
            "agent": "kabir",
            "score": None,
            "status": "ok",
            "summary": "DB health unavailable (database not reachable from this process)",
            "kpis": kpis,
            "actions": ["Verify DATABASE_URL + Postgres reachable for DB reliability checks"],
            "ts": int(time.time()),
        }

    score = _clamp(sum(sub_scores) / len(sub_scores)) if sub_scores else None
    result = {
        "role": "dbre",
        "agent": "kabir",
        "score": round(score, 1) if score is not None else None,
        "status": "ok",
        "summary": (
            f"DB reliability {score:.0f}/100 · {kpis.get('active_connections', '?')} conns · "
            f"{kpis.get('unused_indexes', '?')} unused idx"
            if score is not None
            else "no DB signals"
        ),
        "kpis": kpis,
        "actions": actions,
        "ts": int(time.time()),
    }
    _try_log(
        "kabir", "db_health", json.dumps({"score": score, "conns": kpis.get("active_connections")})
    )
    _maybe_alert(result)
    return result


# --------------------------------------------------------------------------- #
# Aryan — Dependency / Supply-chain Engineer (council 2026-06-25)
#   Distinct from Arnav (secrets/compliance posture): Aryan owns PACKAGE
#   vulnerabilities. Runs pip-audit READ-ONLY (audits installed pkgs, never
#   installs/upgrades). Proposal-only output. pip-audit absent -> neutral +
#   action (loop ready; full activation = add pip-audit to image).
# --------------------------------------------------------------------------- #
def run_deps() -> dict[str, Any]:
    if not _flag_on(_DEPS_FLAG):
        return _disabled_result("deps", _DEPS_FLAG)

    kpis: dict[str, Any] = {}
    actions: list[str] = []
    sub_scores: list[float] = []

    # 1) Lock-file presence (supply-chain pinning hygiene).
    lock = Path("requirements.lock.txt")
    age = _file_age_hours(lock)
    if age is None:
        age = _file_age_hours(Path("requirements.txt"))
    if age is None:
        kpis["lock_age_days"] = None
        sub_scores.append(50.0)
        actions.append("No requirements lock/txt found — pin dependencies for reproducible builds")
    else:
        kpis["lock_age_days"] = round(age / 24.0, 1)
        sub_scores.append(100.0)  # presence is good; staleness alone is not a failure

    # 2) Known CVEs via pip-audit (read-only subprocess; bounded; fail-open).
    try:
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-f", "json", "--progress-spinner=off"],
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (proc.stdout or "").strip()
        data = json.loads(out)  # raises if pip-audit absent / no JSON → caught below
        deps = data.get("dependencies", data) if isinstance(data, dict) else data
        vulns = sum(len(d.get("vulns") or []) for d in (deps or []) if isinstance(d, dict))
        kpis["known_vulnerabilities"] = vulns
        if vulns == 0:
            sub_scores.append(100.0)
        elif vulns <= 3:
            sub_scores.append(60.0)
            actions.append(
                f"{vulns} dependency CVEs — review pip-audit, plan upgrades (never auto)"
            )
        else:
            sub_scores.append(20.0)
            actions.append(f"{vulns} dependency CVEs — prioritize upgrades (proposal-only)")
    except Exception:
        kpis["known_vulnerabilities"] = None
        actions.append("pip-audit unavailable — add 'pip-audit' to image for CVE scanning")

    score = _clamp(sum(sub_scores) / len(sub_scores)) if sub_scores else None
    result = {
        "role": "deps",
        "agent": "aryan",
        "score": round(score, 1) if score is not None else None,
        "status": "ok",
        "summary": (
            f"Supply-chain {score:.0f}/100 · CVEs: {kpis.get('known_vulnerabilities', 'n/a')}"
            if score is not None
            else "no dependency signals"
        ),
        "kpis": kpis,
        "actions": actions,
        "ts": int(time.time()),
    }
    _try_log(
        "aryan",
        "dep_audit",
        json.dumps({"score": score, "vulns": kpis.get("known_vulnerabilities")}),
    )
    _maybe_alert(result)
    return result


# --------------------------------------------------------------------------- #
# Diya — Data-Integrity Engineer (council 2026-06-25)
#   Revenue-adjacent: dupe/incomplete leads = wasted outreach + bad CRM = churn.
#   Scans the prospect store READ-ONLY and REPORTS (never deletes; dedupe stays
#   a human-approved admin action). Empty store -> neutral.
# --------------------------------------------------------------------------- #
def run_dataquality() -> dict[str, Any]:
    if not _flag_on(_DATA_INTEGRITY_FLAG):
        return _disabled_result("dataquality", _DATA_INTEGRITY_FLAG)

    kpis: dict[str, Any] = {}
    actions: list[str] = []
    sub_scores: list[float] = []

    total = 0
    missing = 0
    dup_phone = 0
    dup_email = 0
    seen_phone: set[str] = set()
    seen_email: set[str] = set()
    prospects = _DATA_DIR / "prospects.jsonl"
    try:
        if prospects.exists():
            for line in prospects.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                total += 1
                ph = str(rec.get("phone") or "").strip()
                em = str(rec.get("email") or "").strip().lower()
                if not ph and not em:
                    missing += 1
                if ph:
                    if ph in seen_phone:
                        dup_phone += 1
                    else:
                        seen_phone.add(ph)
                if em:
                    if em in seen_email:
                        dup_email += 1
                    else:
                        seen_email.add(em)
    except Exception:
        pass

    kpis["total_prospects"] = total
    kpis["duplicate_phone"] = dup_phone
    kpis["duplicate_email"] = dup_email
    kpis["missing_contact"] = missing

    if total == 0:
        return {
            "role": "dataquality",
            "agent": "diya",
            "score": None,
            "status": "ok",
            "summary": "No prospects yet — data-integrity scan idle",
            "kpis": kpis,
            "actions": [],
            "ts": int(time.time()),
        }

    dupes = dup_phone + dup_email
    dup_ratio = dupes / total
    miss_ratio = missing / total

    if dup_ratio < 0.02:
        sub_scores.append(100.0)
    elif dup_ratio < 0.10:
        sub_scores.append(70.0)
        actions.append(
            f"{dupes} duplicate leads ({dup_ratio * 100:.0f}%) — review dedupe (report-only)"
        )
    else:
        sub_scores.append(30.0)
        actions.append(
            f"{dupes} duplicate leads ({dup_ratio * 100:.0f}%) — high dup rate, dedupe recommended"
        )

    if miss_ratio < 0.05:
        sub_scores.append(100.0)
    elif miss_ratio < 0.20:
        sub_scores.append(70.0)
        actions.append(f"{missing} leads missing phone+email — enrich before outreach")
    else:
        sub_scores.append(40.0)
        actions.append(
            f"{missing} leads ({miss_ratio * 100:.0f}%) have no contact — enrichment needed"
        )

    score = _clamp(sum(sub_scores) / len(sub_scores)) if sub_scores else None
    result = {
        "role": "dataquality",
        "agent": "diya",
        "score": round(score, 1) if score is not None else None,
        "status": "ok",
        "summary": (
            f"Data integrity {score:.0f}/100 · {total} leads · {dupes} dupes · {missing} no-contact"
        ),
        "kpis": kpis,
        "actions": actions,
        "ts": int(time.time()),
    }
    _try_log("diya", "data_integrity", json.dumps({"score": score, "total": total, "dupes": dupes}))
    _maybe_alert(result)
    return result


# --------------------------------------------------------------------------- #
# Public dispatch
# --------------------------------------------------------------------------- #
_AGENTS = {
    "sre": run_sre,
    "finops": run_finops,
    "security": run_security,
    "dbre": run_dbre,
    "deps": run_deps,
    "dataquality": run_dataquality,
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
    """Run all engineer agents — dashboard rollup."""
    return {role: fn() for role, fn in _AGENTS.items()}


# role -> agent display-name (single source for API/UI; keep in sync with run_X agent= ).
AGENT_NAMES = {
    "sre": "pranav",
    "finops": "vidya",
    "security": "arnav",
    "dbre": "kabir",
    "deps": "aryan",
    "dataquality": "diya",
}


def roles() -> list[str]:
    """All engineer-agent role keys — drift-proof source for the admin API/UI."""
    return list(_AGENTS)


__all__ = [
    "run",
    "run_all",
    "run_sre",
    "run_finops",
    "run_security",
    "compute_security_posture",
    "run_dbre",
    "run_deps",
    "run_dataquality",
    "roles",
    "AGENT_NAMES",
]
