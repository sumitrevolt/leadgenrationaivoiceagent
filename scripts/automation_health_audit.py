#!/usr/bin/env python3
"""
Automation Health Audit — Daily/Weekly/Monthly checks for self-improve loop.

Usage:
  python scripts/automation_health_audit.py --daily-check
  python scripts/automation_health_audit.py --weekly-audit
  python scripts/automation_health_audit.py --monthly-report
  python scripts/automation_health_audit.py --anomalies
  python scripts/automation_health_audit.py --approvals-pending
  python scripts/automation_health_audit.py --dlq-status
  python scripts/automation_health_audit.py --llm-status
  python scripts/automation_health_audit.py --compliance-check

Output:
  Default: Human-readable console (colored)
  --format=json: Machine-readable JSON
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.platform import automation_health, skill_library
except ImportError:
    automation_health = None
    skill_library = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    """Read JSONL file safely."""
    rows = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _read_json(path: str) -> dict[str, Any]:
    """Read JSON file safely."""
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _flag(name: str, default: bool = False) -> bool:
    v = (os.environ.get(name, "") or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _known_heartbeat_times(beats: dict[str, Any]) -> list[datetime]:
    rows: list[datetime] = []
    known = (
        set(getattr(automation_health, "EXPECTED_GAP_MIN", {}).keys())
        if automation_health
        else set()
    )
    for job, rec in beats.items():
        if known and job not in known:
            continue
        try:
            raw = str((rec or {}).get("at") or "")
            if not raw:
                continue
            ts = datetime.fromisoformat(raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            rows.append(ts)
        except Exception:
            pass
    return rows


# ============================================================================
# CHECKS
# ============================================================================


def check_alive() -> dict[str, Any]:
    """Is the self-improve loop alive? (heartbeat check)."""
    state = _read_json("data/self_improve_state.json")
    beats = _read_json("data/job_heartbeats.json")

    status = "green"
    last_tick_min = -1
    worker_ping_ms = -1
    detail = ""

    self_improve_on = _flag("SELF_IMPROVE_LOOP", False)
    team_auto_on = _flag("TEAM_AUTOMATION", False)

    if state.get("last_tick_at") or state.get("last_tick"):
        try:
            raw = state.get("last_tick_at", "")
            if raw:
                last_tick_time = datetime.fromisoformat(raw)
                if last_tick_time.tzinfo is None:
                    last_tick_time = last_tick_time.replace(tzinfo=timezone.utc)
            else:
                last_tick_time = datetime.fromtimestamp(
                    float(state.get("last_tick", 0)), timezone.utc
                )
            last_tick_min = int(((_now() - last_tick_time).total_seconds()) / 60)

            if last_tick_min < 10:
                status = "green"
                detail = f"Self-improve loop ticking normally ({last_tick_min}m ago)"
            elif last_tick_min < 30:
                status = "yellow"
                detail = f"Self-improve loop running but slow ({last_tick_min}m ago)"
            else:
                status = "red"
                detail = f"Self-improve loop stuck or paused ({last_tick_min}m ago)"
            return {
                "status": status,
                "last_tick_min": last_tick_min,
                "worker_ping_ms": worker_ping_ms,
                "detail": detail,
            }
        except Exception:
            pass

    beat_times = _known_heartbeat_times(beats)
    if beat_times:
        newest = max(beat_times)
        last_tick_min = int(((_now() - newest).total_seconds()) / 60)
        if last_tick_min < 30:
            status = "green"
            detail = f"Scheduler heartbeat fresh ({last_tick_min}m ago)"
        elif last_tick_min < 120:
            status = "yellow"
            detail = f"Scheduler heartbeat slow ({last_tick_min}m ago)"
        else:
            if self_improve_on or team_auto_on:
                status = "red"
                detail = f"Scheduler heartbeat stale ({last_tick_min}m ago)"
            else:
                status = "green"
                detail = f"Historical scheduler heartbeat stale ({last_tick_min}m ago); loop not enabled now"
    elif self_improve_on or team_auto_on:
        status = "red"
        detail = "No heartbeat found even though always-on automation is enabled"
    else:
        status = "green"
        detail = "No always-on loop enabled in this environment"

    return {
        "status": status,
        "last_tick_min": last_tick_min,
        "worker_ping_ms": worker_ping_ms,
        "detail": detail,
    }


def check_budget() -> dict[str, Any]:
    """Cost tracking — spent vs. cap."""
    runs = _read_jsonl("data/self_improve_runs.jsonl")

    today_key = _now().strftime("%Y-%m-%d")
    today_runs = [r for r in runs if r.get("at", "").startswith(today_key)]

    total_cost = sum(float(r.get("cost", 0)) for r in today_runs)
    cap = float(os.environ.get("SELFIMPROVE_COST_CAP", "50"))

    percent = int(total_cost / cap * 100) if cap > 0 else 0

    status = "green"
    if percent > 80:
        status = "red"
    elif percent > 40:
        status = "yellow"

    # Trending
    if today_runs:
        avg_cost_per_run = total_cost / len(today_runs)
        runs_per_hour = len(today_runs) / max(((_now().hour % 24) + 1), 1)
        estimated_eod = total_cost + (avg_cost_per_run * runs_per_hour * (24 - _now().hour))
    else:
        estimated_eod = 0

    # Top expensive actions
    action_costs = {}
    for r in today_runs:
        action = r.get("action", "unknown")
        cost = float(r.get("cost", 0))
        action_costs[action] = action_costs.get(action, 0) + cost

    top_actions = sorted(action_costs.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "status": status,
        "spent": round(total_cost, 2),
        "cap": cap,
        "percent": percent,
        "runs_today": len(today_runs),
        "estimated_eod": round(estimated_eod, 2),
        "top_actions": [{"action": a, "cost": round(c, 2)} for a, c in top_actions],
    }


def check_anomalies() -> dict[str, Any]:
    """Task success rates + errors."""
    if not skill_library:
        return {"status": "unknown", "message": "skill_library not available"}

    try:
        stats = skill_library.stats()

        low_success = [
            {"action": a, "success_rate": round(d["rate"], 3), "uses": d["uses"]}
            for a, d in stats.items()
            if d["rate"] < 0.5 and d["uses"] >= 3
        ]

        # Real DLQ depth (Redis dlq:failed_tasks + dlq:dead), same source as
        # `--dlq-status`. `data/dlq_failed_tasks.jsonl` is legacy/dev-only and
        # is never written in prod (DLQ lives in Redis) — reading it here
        # always reported 0 and masked a real backlog.
        dlq_status = check_dlq_status()
        depths = dlq_status.get("depths", {})
        dlq_depth = sum(v for v in (depths.get("dlq", -1), depths.get("dead", -1)) if v > 0)

        status = "green"
        if dlq_depth > 10:
            status = "red"
        elif dlq_depth > 5:
            status = "yellow"
        elif low_success:
            status = "yellow"

        return {
            "status": status,
            "dlq_depth": dlq_depth,
            "low_success_actions": low_success,
            "total_actions_tracked": len(stats),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_approvals() -> dict[str, Any]:
    """Approval queue status (if enabled)."""
    if os.environ.get("SELF_IMPROVE_APPROVAL", "0").lower() not in ("1", "true"):
        return {"enabled": False}

    queue = _read_jsonl("data/self_improve_queue.jsonl")
    pending = [q for q in queue if q.get("status") == "pending"]

    if pending:
        oldest = min(pending, key=lambda x: x.get("at", "9999"))
        oldest_min = int(
            ((_now() - datetime.fromisoformat(oldest["at"].replace("Z", "+00:00"))).total_seconds())
            / 60
        )
    else:
        oldest_min = 0

    status = "green"
    if len(pending) > 5:
        status = "red"
    elif len(pending) > 2:
        status = "yellow"

    return {
        "enabled": True,
        "status": status,
        "pending_count": len(pending),
        "oldest_pending_min": oldest_min,
    }


def check_next_action() -> dict[str, Any]:
    """What's running now + what's queued."""
    state = _read_json("data/self_improve_state.json")
    runs = _read_jsonl("data/self_improve_runs.jsonl")
    queue = _read_jsonl("data/self_improve_queue.jsonl")

    current = None
    if runs:
        last = runs[-1]
        if last.get("status") == "running":
            current = last.get("action", "?")

    pending_queue = [q for q in queue if q.get("status") == "pending"]

    try:
        stats = skill_library.stats() if skill_library else {}
        next_pick = (
            max(stats.items(), key=lambda kv: kv[1].get("rate", 0.5))[0] if stats else "unknown"
        )
    except Exception:
        next_pick = "unknown"

    return {
        "current_action": current,
        "queue_pending": len(pending_queue),
        "next_auto_pick": next_pick,
    }


def check_dlq_status() -> dict[str, Any]:
    """Actual Redis-backed DLQ status, with legacy JSONL fallback for old dev data."""
    depths = {"celery": -1, "heavy": -1, "dlq": -1, "dead": -1}
    recent_failed: list[Any] = []
    recent_dead: list[Any] = []

    try:
        if automation_health:
            depths.update(automation_health.queue_depth())
    except Exception:
        pass

    try:
        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)
        raw_failed = r.lrange("dlq:failed_tasks", 0, 9) or []
        raw_dead = r.lrange("dlq:dead", 0, 9) or []

        def _decode_rows(rows: list[Any]) -> list[Any]:
            out: list[Any] = []
            for row in rows:
                if isinstance(row, bytes):
                    row = row.decode("utf-8", errors="replace")
                try:
                    out.append(json.loads(row))
                except Exception:
                    out.append(str(row))
            return out

        recent_failed = _decode_rows(raw_failed)
        recent_dead = _decode_rows(raw_dead)
    except Exception:
        legacy = _read_jsonl("data/dlq_failed_tasks.jsonl")
        if depths.get("dlq", -1) < 0 and legacy:
            depths["dlq"] = len(legacy)
        recent_failed = legacy[-10:]

    total_known = sum(v for v in (depths.get("dlq", -1), depths.get("dead", -1)) if v >= 0)
    status = "green"
    if depths.get("dead", 0) > 0 or total_known > 10:
        status = "red"
    elif total_known > 0:
        status = "yellow"
    elif depths.get("dlq", -1) < 0 and depths.get("dead", -1) < 0:
        status = "unknown"

    return {
        "status": status,
        "depths": depths,
        "recent_failed": recent_failed,
        "recent_dead": recent_dead,
    }


def _optout_ledger_writable() -> bool:
    """Real opt-out enforcement is app.telephony.consent_ledger (JSONL +
    optional Postgres dual-write), wired into ComplianceGate.check() step 2.5
    — NOT a `data/dnd_cache.json` file (no code path ever writes that file,
    so an mtime-freshness check on it always reported "stale"). A quiet day
    with zero new opt-outs is healthy, not stale — so check the real store
    is reachable/writable instead of guessing from file age."""
    try:
        from app.telephony.consent_ledger import suppression_path

        # Resolved per call, not imported as a constant: an audit that froze the
        # path at import would keep reporting on the pre-cutover location.
        d = suppression_path().parent
        return os.path.isdir(d) and os.access(d, os.W_OK)
    except Exception:
        return False


def check_compliance() -> dict[str, Any]:
    """DLT, opt-out, recording, approvals."""
    dlt_enabled = _flag("DLT_APPROVED", False) or _flag("ENABLE_DLT", False)
    opt_out_recent = _optout_ledger_writable()

    retention_enabled = _flag("RECORDING_RETENTION", False)
    approval_mode = _flag("SELF_IMPROVE_APPROVAL", False)
    email_outreach_on = _flag("AUTO_EMAIL_OUTREACH", False)
    sms_dlt_on = _flag("SMS_DLT_ENABLED", False)
    self_improve_on = _flag("SELF_IMPROVE_LOOP", False)
    telephony_configured = bool((os.environ.get("VOBIZ_AUTH_ID", "") or "").strip())
    cold_calling_on = dlt_enabled and bool((os.environ.get("VOBIZ_CALLER_ID", "") or "").strip())
    outbound_scope = email_outreach_on or sms_dlt_on or cold_calling_on

    status = "green"
    issues = []

    if cold_calling_on and not dlt_enabled:
        issues.append("DLT not enabled (need for cold calls)")
        status = "yellow"

    if outbound_scope and not opt_out_recent:
        issues.append("Opt-out ledger (consent_ledger) store not writable")
        status = "yellow"

    if telephony_configured and not retention_enabled:
        issues.append("Recording retention not active")
        status = "yellow"

    if self_improve_on and not approval_mode:
        issues.append("High-risk approval mode OFF (consider enabling)")
        status = "yellow"

    return {
        "status": status,
        "dlt_enabled": dlt_enabled if cold_calling_on else True,
        "optout_enforced": opt_out_recent if outbound_scope else True,
        "retention_active": retention_enabled if telephony_configured else True,
        "approval_mode": approval_mode if self_improve_on else True,
        "issues": issues,
    }


# ============================================================================
# FORMATTERS
# ============================================================================


def format_daily_check_human() -> str:
    """Human-readable daily standup."""
    alive = check_alive()
    budget = check_budget()
    anomalies = check_anomalies()
    approvals = check_approvals()
    next_action = check_next_action()
    compliance = check_compliance()

    status_icons = {"green": "✅", "yellow": "🟡", "red": "🔴", "unknown": "❓"}

    output = []
    output.append("╔════════════════════════════════════════════════════════╗")
    output.append(f"║ AUTOMATION HEALTH CHECK — {_now().strftime('%Y-%m-%d %H:%M:%S')}Z        ║")
    output.append("╚════════════════════════════════════════════════════════╝")
    output.append("")

    # 1. ALIVE
    icon = status_icons.get(alive["status"], "?")
    output.append(f"1. LOOP ALIVE {icon}")
    output.append(f"   {alive['detail']}")
    if alive["last_tick_min"] >= 0:
        output.append(f"   Last tick: {alive['last_tick_min']}m ago")
    output.append("")

    # 2. BUDGET
    icon = status_icons.get(budget["status"], "?")
    output.append(f"2. BUDGET {icon}")
    output.append(
        f"   Today Spend: ${budget['spent']:.2f} / ${budget['cap']:.2f} ({budget['percent']}%)"
    )
    output.append(f"   Estimated EOD: ${budget['estimated_eod']:.2f}")
    if budget["top_actions"]:
        output.append("   Top actions by cost:")
        for a in budget["top_actions"]:
            output.append(f"     • {a['action']}: ${a['cost']:.2f}")
    output.append("")

    # 3. APPROVALS
    if approvals.get("enabled"):
        icon = status_icons.get(approvals["status"], "?")
        output.append(f"3. APPROVALS {icon}")
        output.append(f"   Pending: {approvals['pending_count']}")
        if approvals["oldest_pending_min"] > 0:
            output.append(f"   Oldest: {approvals['oldest_pending_min']}m ago")
    else:
        output.append("3. APPROVALS")
        output.append("   Status: Disabled (SELF_IMPROVE_APPROVAL=0)")
    output.append("")

    # 4. ANOMALIES
    icon = status_icons.get(anomalies["status"], "?")
    output.append(f"4. ANOMALIES {icon}")
    if anomalies.get("message"):
        output.append(f"   {anomalies['message']}")
    else:
        output.append(f"   DLQ Depth: {anomalies['dlq_depth']}")
        output.append(f"   Actions Tracked: {anomalies['total_actions_tracked']}")
        if anomalies["low_success_actions"]:
            output.append("   Low-Success Actions (<50%):")
            for a in anomalies["low_success_actions"]:
                output.append(
                    f"     • {a['action']}: {a['success_rate'] * 100:.1f}% ({a['uses']} uses)"
                )
    output.append("")

    # 5. NEXT ACTION
    output.append("5. NEXT ACTION")
    output.append(f"   Current: {next_action['current_action'] or 'idle'}")
    output.append(f"   Queue Pending: {next_action['queue_pending']}")
    output.append(f"   Auto-Pick Next: {next_action['next_auto_pick']}")
    output.append("")

    # 6. COMPLIANCE
    icon = status_icons.get(compliance["status"], "?")
    output.append(f"6. COMPLIANCE {icon}")
    output.append(f"   DLT: {'✅' if compliance['dlt_enabled'] else '❌'}")
    output.append(f"   Opt-Out Enforced: {'✅' if compliance['optout_enforced'] else '❌'}")
    output.append(f"   Recording Retention: {'✅' if compliance['retention_active'] else '❌'}")
    output.append(f"   High-Risk Approval: {'✅' if compliance['approval_mode'] else '❌'}")
    if compliance["issues"]:
        output.append("   Issues:")
        for issue in compliance["issues"]:
            output.append(f"     ⚠️  {issue}")
    output.append("")

    # VERDICT
    all_statuses = [alive["status"], budget["status"], anomalies["status"], compliance["status"]]
    if approvals.get("enabled"):
        all_statuses.append(approvals["status"])

    checks_for_verdict = {
        "alive": alive,
        "budget": budget,
        "anomalies": anomalies,
        "approvals": approvals,
        "compliance": compliance,
    }
    verdict = _daily_check_verdict(checks_for_verdict)
    verdict_icon = status_icons.get(verdict, "?")
    verdict_text = (
        "All green — loop healthy"
        if verdict == "green"
        else "Issues detected — investigate"
        if verdict == "red"
        else "Minor issues — monitor"
    )

    output.append("═══════════════════════════════════════════════════════════")
    output.append(f"VERDICT: {verdict_icon} {verdict_text.upper()}")
    output.append("═══════════════════════════════════════════════════════════")

    return "\n".join(output)


def _daily_check_verdict(checks: dict) -> str:
    """Aggregate per-check status → green|yellow|red (shared by human + JSON)."""
    all_statuses = [
        (checks.get("alive") or {}).get("status"),
        (checks.get("budget") or {}).get("status"),
        (checks.get("anomalies") or {}).get("status"),
        (checks.get("compliance") or {}).get("status"),
    ]
    approvals = checks.get("approvals") or {}
    if approvals.get("enabled"):
        all_statuses.append(approvals.get("status"))
    statuses = [s for s in all_statuses if s]
    if not statuses:
        return "yellow"
    if all(s == "green" for s in statuses):
        return "green"
    if "red" in statuses:
        return "red"
    return "yellow"


def format_daily_check_json() -> str:
    """JSON format for daily check — verdict matches human formatter (ADR-114)."""
    checks = {
        "alive": check_alive(),
        "budget": check_budget(),
        "anomalies": check_anomalies(),
        "approvals": check_approvals(),
        "next_action": check_next_action(),
        "compliance": check_compliance(),
    }
    return json.dumps(
        {
            "timestamp": _now().isoformat(),
            "checks": checks,
            "verdict": _daily_check_verdict(checks),
        },
        indent=2,
    )


def format_weekly_audit_human() -> str:
    """Human-readable weekly audit."""
    output = []
    output.append("╔════════════════════════════════════════════════════════╗")
    output.append(f"║ WEEKLY AUDIT — {_now().strftime('%Y-%m-%d')}                         ║")
    output.append("╚════════════════════════════════════════════════════════╝")
    output.append("")

    # Success rates
    if skill_library:
        try:
            stats = skill_library.stats()
            best = skill_library.best(5)
            worst = skill_library.worst(5)

            output.append("📊 SKILL SUCCESS RATES")
            output.append("Best:")
            for b in best:
                output.append(f"  ✅ {b['skill']}: {b['rate'] * 100:.1f}% ({b['uses']} uses)")
            output.append("Worst:")
            for w in worst:
                output.append(f"  ⚠️  {w['skill']}: {w['rate'] * 100:.1f}% ({w['uses']} uses)")
        except Exception as e:
            output.append(f"⚠️  Could not read skill stats: {e}")

    output.append("")

    # Cost trends
    budget = check_budget()
    output.append("💰 COST ANALYSIS")
    output.append(f"Today's Spend: ${budget['spent']:.2f} / ${budget['cap']:.2f}")
    output.append(f"Runs: {budget['runs_today']}")

    output.append("")
    output.append("═══════════════════════════════════════════════════════════")

    return "\n".join(output)


def format_monthly_report_human() -> str:
    """Human-readable monthly report."""
    output = []
    output.append("╔════════════════════════════════════════════════════════╗")
    output.append(f"║ MONTHLY REPORT — {_now().strftime('%B %Y')}                       ║")
    output.append("╚════════════════════════════════════════════════════════╝")
    output.append("")

    output.append("See docs/.claude/skills/audit-automation for detailed report template.")
    output.append("For this month: generate via `--weekly-audit` + manual review of:")
    output.append("  1. data/self_improve_runs.jsonl (last 100+ rows)")
    output.append("  2. data/skill_lessons.jsonl (all lessons)")
    output.append("  3. data/job_heartbeats.json (uptime)")

    return "\n".join(output)


# ============================================================================
# MAIN
# ============================================================================


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Automation Loop Health Audit")
    parser.add_argument("--daily-check", action="store_true", help="Quick standup check (5 min)")
    parser.add_argument("--weekly-audit", action="store_true", help="Full weekly audit (15 min)")
    parser.add_argument(
        "--monthly-report", action="store_true", help="Monthly deep-dive report (1 hour)"
    )
    parser.add_argument(
        "--anomalies", action="store_true", help="Detect issues (cost spike, low success, etc.)"
    )
    parser.add_argument(
        "--approvals-pending", action="store_true", help="Show pending approval queue"
    )
    parser.add_argument("--dlq-status", action="store_true", help="Show dead-letter queue")
    parser.add_argument("--llm-status", action="store_true", help="Show LLM provider metrics")
    parser.add_argument("--compliance-check", action="store_true", help="Full compliance audit")
    parser.add_argument(
        "--format", choices=["human", "json"], default="human", help="Output format"
    )

    args = parser.parse_args()

    # Default to daily-check if nothing specified
    if not any(
        [
            args.daily_check,
            args.weekly_audit,
            args.monthly_report,
            args.anomalies,
            args.approvals_pending,
            args.dlq_status,
            args.llm_status,
            args.compliance_check,
        ]
    ):
        args.daily_check = True

    # Execute
    if args.daily_check:
        if args.format == "json":
            print(format_daily_check_json())
        else:
            print(format_daily_check_human())

    elif args.weekly_audit:
        print(format_weekly_audit_human())

    elif args.monthly_report:
        print(format_monthly_report_human())

    elif args.anomalies:
        anomalies = check_anomalies()
        if args.format == "json":
            print(json.dumps(anomalies, indent=2))
        else:
            print(f"Anomalies: {json.dumps(anomalies, indent=2)}")

    elif args.approvals_pending:
        approvals = check_approvals()
        if args.format == "json":
            print(json.dumps(approvals, indent=2))
        else:
            print(f"Approvals: {json.dumps(approvals, indent=2)}")

    elif args.dlq_status:
        dlq = check_dlq_status()
        if args.format == "json":
            print(json.dumps(dlq, indent=2))
        else:
            print(f"DLQ Status: {dlq['status']}")
            print(f"Depths: {json.dumps(dlq['depths'], indent=2)}")
            print(f"Recent Failed: {json.dumps(dlq['recent_failed'], indent=2)}")
            print(f"Recent Dead: {json.dumps(dlq['recent_dead'], indent=2)}")

    elif args.compliance_check:
        compliance = check_compliance()
        if args.format == "json":
            print(json.dumps(compliance, indent=2))
        else:
            print(f"Compliance: {json.dumps(compliance, indent=2)}")


if __name__ == "__main__":
    main()
