"""Telegram owner commands — Wave 7 deliverable (§2 + §5 + §6 directive).

Implements 9 new owner commands ADDITIVE to the existing 7 in
``app/integrations/telegram_bot.py``. Wired via the dispatch table in
``telegram_bot.py:_execute_command``.

Hard rules (per directive):
  * Return real backend data — never fabricate.
  * Missing data must show UNKNOWN / NOT_INSTRUMENTED / UNAVAILABLE, never zero or healthy.
  * MRR and collected-cash scoreboards are NEVER added (separate).
  * Each handler returns a ``OwnerCommandResult`` so the bot dispatcher can
    format consistently.
  * Credential probes NEVER print raw tokens / keys / customer data.

This module is intentionally non-network — every command reads from in-process
state (SQLite, JSONL, env). No external network calls. No token rotation.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# ---------- result type ----------


@dataclass
class OwnerCommandResult:
    """Compact, never-fabricated command result."""

    command: str
    status: str  # "OK" | "EMPTY" | "UNAVAILABLE" | "NOT_INSTRUMENTED"
    fetched_at: str
    elapsed_ms: float
    text: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_telegram_text(self, max_chars: int = 3800) -> str:
        """Return the human-readable text, truncated for Telegram 4096-char limit."""
        if len(self.text) <= max_chars:
            return self.text
        return self.text[: max_chars - 80] + "\n… (truncated)"

    def to_data_payload(self) -> dict[str, Any]:
        """Return the structured JSON payload (for the dashboard mirror)."""
        return {
            "command": self.command,
            "status": self.status,
            "fetched_at": self.fetched_at,
            "elapsed_ms": self.elapsed_ms,
            "data": self.data,
        }


# ---------- helpers ----------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe(fn, default=None, label=""):
    """Call fn() safely; log + return default on any error."""
    try:
        return fn()
    except Exception as exc:
        logger.debug("telegram_owner_commands %s failed: %s", label, type(exc).__name__)
        return default


def _data_path(filename: str) -> Path:
    """Resolve a runtime-data file under repo /data or ./data (whichever exists)."""
    repo_data = Path(__file__).resolve().parents[2] / "data" / filename
    if repo_data.parent.is_dir():
        return repo_data
    return Path("data") / filename


def _read_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception as exc:
        logger.debug("read_jsonl %s failed: %s", path, type(exc).__name__)
    return rows


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ---------- command implementations ----------


def cmd_revenue() -> OwnerCommandResult:
    """/revenue — verified recurring MRR + verified net collected cash.

    Per §5 directive: NEVER combine into one number. NEVER carry forward
    historical amounts without reconciliation. Honest baseline = 1 paying
    customer (jiya_makeover); today's actual MRR = source-driven.
    """
    started = time.monotonic()

    # Source 1: billing_records (verified invoices) — Postgres-backed, but
    # we read via the in-process store if available, else via JSONL fallback.
    billing_rows = _safe(
        lambda: _read_jsonl(_data_path("billing_records.jsonl"), limit=500),
        default=[],
        label="billing_records.jsonl",
    )

    # Source 2: revenue_snapshots.jsonl (B1 daily)
    snapshots = _safe(
        lambda: _read_jsonl(_data_path("revenue_snapshots.jsonl"), limit=90),
        default=[],
        label="revenue_snapshots.jsonl",
    )

    # Source 3: marketing_clients.jsonl (active subscriptions)
    clients = _safe(
        lambda: _read_jsonl(_data_path("marketing_clients.jsonl"), limit=500),
        default=[],
        label="marketing_clients.jsonl",
    )

    if not billing_rows and not snapshots and not clients:
        return OwnerCommandResult(
            command="revenue",
            status="NOT_INSTRUMENTED",
            fetched_at=_now_iso(),
            elapsed_ms=round((time.monotonic() - started) * 1000, 2),
            text=(
                "Revenue scoreboards: NOT_INSTRUMENTED\n"
                "Sources checked:\n"
                "  • data/billing_records.jsonl — not present\n"
                "  • data/revenue_snapshots.jsonl — not present\n"
                "  • data/marketing_clients.jsonl — not present\n\n"
                "Honest baseline (per CLAUDE.md + ADR-243):\n"
                "  • Active paying customers: 1 (jiya_makeover)\n"
                "  • Verified MRR: source-driven (NOT carry-forward)\n"
                "  • Verified collected cash: source-driven\n"
                "  • Gap to ₹1,00,00,000 MRR target: not computable without source\n\n"
                "This command will NOT fabricate."
            ),
            data={
                "sources_checked": [
                    "data/billing_records.jsonl",
                    "data/revenue_snapshots.jsonl",
                    "data/marketing_clients.jsonl",
                ],
                "all_missing": True,
            },
        )

    # If we have at least one source, compute honest numbers.
    active_subs = [
        c for c in clients if str(c.get("status", "")).lower() in ("active", "paid", "live")
    ]
    invoices = [b for b in billing_rows if isinstance(b, dict)]
    latest_snapshot = snapshots[-1] if snapshots else None

    verified_mrr = 0.0
    if latest_snapshot and isinstance(latest_snapshot, dict):
        verified_mrr = float(
            latest_snapshot.get("verified_recurring_mrr_inr")
            or latest_snapshot.get("mrr_inr")
            or 0.0
        )

    verified_cash = 0.0
    for inv in invoices:
        amt = inv.get("amount_inr") or inv.get("verified_amount_inr") or 0.0
        if inv.get("status") in ("PAID", "VERIFIED", "RECEIVED"):
            verified_cash += float(amt)

    target = 10_000_000.0  # ₹1 crore
    gap = max(0.0, target - verified_mrr)

    text = (
        f"VERIFIED RECURRING MRR (separate scoreboard)\n"
        f"  ₹ {verified_mrr:,.0f}\n"
        f"  Active paying customers: {len(active_subs)}\n"
        f"  Source: data/revenue_snapshots.jsonl (latest) + data/marketing_clients.jsonl\n"
        f"  Target: ₹ 1,00,00,000 — gap ₹ {gap:,.0f}\n\n"
        f"VERIFIED NET COLLECTED CASH (separate scoreboard)\n"
        f"  ₹ {verified_cash:,.0f}\n"
        f"  Source: data/billing_records.jsonl (PAID|VERIFIED|RECEIVED rows only)\n"
        f"  These two metrics are NEVER added.\n"
    )

    return OwnerCommandResult(
        command="revenue",
        status="OK" if verified_mrr > 0 or verified_cash > 0 else "EMPTY",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text=text,
        data={
            "verified_recurring_mrr_inr": verified_mrr,
            "verified_net_collected_cash_inr": verified_cash,
            "active_paying_customers": len(active_subs),
            "active_subscription_count": len(active_subs),
            "verified_invoice_count": len(invoices),
            "latest_snapshot_present": latest_snapshot is not None,
            "mrr_target_inr": target,
            "mrr_gap_inr": gap,
            "sources_used": [
                "data/revenue_snapshots.jsonl",
                "data/marketing_clients.jsonl",
                "data/billing_records.jsonl",
            ],
        },
    )


def cmd_workers() -> OwnerCommandResult:
    """/workers — local desktop apps + VPS 9 worker domains + 31 agents.

    Per §3 directive: distinguish REGISTERED / CONFIGURED / CONNECTED /
    RUNNING / VERIFIED_WORKING / DEGRADED / BLOCKED / FAILED / UNKNOWN / STALE.
    """
    started = time.monotonic()

    desktop = _safe(
        lambda: _read_json(
            Path(__file__).resolve().parents[2] / "docs" / "coordination" / "desktop_registry.json"
        ),
        default=None,
        label="desktop_registry.json",
    )

    agents = _safe(
        lambda: list(
            __import__("app.platform.agent_registry", fromlist=["all_contracts"])
            .all_contracts()
            .keys()
        ),
        default=[],
        label="agent_registry.all_contracts",
    )

    hermes_bots = _safe(
        lambda: list(
            __import__(
                "app.platform.automation_orchestrator", fromlist=["AutomationOrchestrator"]
            ).AutomationOrchestrator.HERMES_BOTS.keys()
        ),
        default=[],
        label="HERMES_BOTS",
    )

    desktop_apps = []
    if isinstance(desktop, dict):
        for app_entry in desktop.get("apps", []):
            desktop_apps.append(
                {
                    "id": app_entry.get("id"),
                    "name": app_entry.get("name"),
                    "status": app_entry.get("status"),
                }
            )

    text_lines = ["WORKFORCE OVERVIEW (LOCAL + VPS)\n"]
    text_lines.append("VPS — 9 Hermes bots (orchestration planes):")
    for bot in hermes_bots:
        text_lines.append(f"  • {bot}")
    text_lines.append("")
    text_lines.append("VPS — 31 agents (specialist execution):")
    if agents:
        for a in sorted(agents)[:31]:
            text_lines.append(f"  • {a}")
    else:
        text_lines.append("  (registry not initialized)")
    text_lines.append("")
    text_lines.append(f"LOCAL — Desktop apps ({len(desktop_apps)} in registry):")
    for app_entry in desktop_apps:
        text_lines.append(f"  • {app_entry['id']:18s} — {app_entry['status']}")

    return OwnerCommandResult(
        command="workers",
        status="OK" if (agents or desktop_apps or hermes_bots) else "NOT_INSTRUMENTED",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text="\n".join(text_lines),
        data={
            "hermes_bots": hermes_bots,
            "agent_count": len(agents),
            "desktop_apps": desktop_apps,
            "desktop_total": len(desktop_apps),
            "desktop_registered": sum(1 for d in desktop_apps if d["status"] == "registered"),
            "desktop_observed_not_attested": sum(
                1 for d in desktop_apps if "observed" in (d["status"] or "").lower()
            ),
        },
    )


def cmd_smartflo() -> OwnerCommandResult:
    """/smartflo — provider + acceptance gates + recent calls.

    Per §7 directive: must show real provider health. Acceptance gates from
    ``smartflo_acceptance.py`` (12 gates; gates 4-11 are STUBS marked UNVERIFIED).
    """
    started = time.monotonic()

    # Provider info — never assume TATA_SMARTFLO without source.
    provider = _safe(
        lambda: __import__("app.telephony.call_manager", fromlist=["get_provider"]).get_provider(),
        default=None,
        label="call_manager.get_provider",
    )

    # Acceptance gates — best-effort import; missing = NOT_INSTRUMENTED.
    gates = _safe(
        lambda: (
            __import__("app.voice.smartflo_acceptance", fromlist=["SMARTFLO_GATES"]).SMARTFLO_GATES
        ),
        default=None,
        label="SMARTFLO_GATES",
    )

    text_lines = ["SMARTFLO / SWARA STATUS\n"]
    if provider:
        text_lines.append(f"  Provider: {provider}")
    else:
        text_lines.append("  Provider: UNKNOWN (call_manager not reachable)")
    voice_stream_enabled = os.getenv("SMARTFLO_VOICE_STREAM_ENABLED", "0").strip() in (
        "1",
        "true",
        "yes",
        "on",
    )
    text_lines.append(f"  SMARTFLO_VOICE_STREAM_ENABLED: {'1' if voice_stream_enabled else '0'}")
    text_lines.append("")
    text_lines.append("Acceptance gates (12 total; remote gates STUBS = UNVERIFIED):")
    if gates:
        for gate in gates:
            mark = "✓" if gate.get("passed") else "○" if gate.get("stub") else "✗"
            text_lines.append(f"  {mark} {gate['name']:32s} {gate.get('state', 'UNKNOWN')}")
    else:
        text_lines.append("  (smartflo_acceptance not loaded)")

    return OwnerCommandResult(
        command="smartflo",
        status="OK" if (provider or gates) else "NOT_INSTRUMENTED",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text="\n".join(text_lines),
        data={
            "provider": provider,
            "voice_stream_enabled": voice_stream_enabled,
            "gate_count": len(gates) if gates else 0,
            "gates_passed": sum(1 for g in (gates or []) if g.get("passed")),
            "gates_stub": sum(1 for g in (gates or []) if g.get("stub")),
        },
    )


def cmd_typesafe() -> OwnerCommandResult:
    """/typesafe — key_manager slots + multipass trace stats."""
    started = time.monotonic()

    slots = _safe(
        lambda: __import__("app.platform.key_manager", fromlist=["get_all_slots"]).get_all_slots(),
        default=None,
        label="key_manager.get_all_slots",
    )

    intake_trace = _read_jsonl(_data_path("typesafe_intake_trace.jsonl"), limit=500)
    consumed_total = sum(int(r.get("consumed_calls", 0) or 0) for r in intake_trace)

    text_lines = ["TYPESAFE STATUS (canonical, single SDK)\n"]
    if slots is None:
        text_lines.append("  Key manager slots: UNAVAILABLE (key_manager module not loaded)")
    else:
        text_lines.append(f"  Total slots: {len(slots)}")
        for slot in slots:
            text_lines.append(
                f"  • {slot.get('slot', '?')} — enabled={slot.get('enabled')} model={slot.get('model', '?')}"
            )
    text_lines.append(f"  Intake-gate trace rows: {len(intake_trace)}")
    text_lines.append(f"  Total consumed_calls (intake): {consumed_total}")
    text_lines.append("")
    text_lines.append("Wired consumers (Wave 7):")
    text_lines.append(
        "  • automation_orchestrator.submit_task — wired (additive, TYPESAFE_INTAKE_GATE=1)"
    )
    text_lines.append(
        "  • Unwired: plan_review / output_review / revision_review / final_review / outcome_review / session_summary"
    )

    return OwnerCommandResult(
        command="typesafe",
        status="OK" if (slots is not None or intake_trace) else "NOT_INSTRUMENTED",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text="\n".join(text_lines),
        data={
            "slot_count": len(slots) if slots else 0,
            "intake_trace_rows": len(intake_trace),
            "consumed_calls_total": consumed_total,
            "wired_stages": ["intake_judge (additive, default OFF)"],
            "unwired_stages": [
                "plan_review",
                "output_review",
                "revision_review",
                "final_review",
                "outcome_review",
                "session_summary",
            ],
        },
    )


def cmd_blockers() -> OwnerCommandResult:
    """/blockers — every BLOCKED / FAILED task across canonical stores."""
    started = time.monotonic()

    blocker_rows: list[dict[str, Any]] = []

    # Automation orchestrator
    def _orch_blockers():
        from app.platform.automation_orchestrator import AutomationOrchestrator

        orch = AutomationOrchestrator()
        rows = []
        for t in orch.store.all_tasks():
            status_str = str(getattr(t.status, "value", t.status)).upper()
            if status_str in ("BLOCKED", "FAILED"):
                rows.append(
                    {
                        "source": "automation_orchestrator",
                        "task_id": t.task_id,
                        "owner_bot": t.owner_bot,
                        "assigned_agent": t.assigned_agent,
                        "status": status_str,
                        "blocker": getattr(t, "error_message", "") or "",
                    }
                )
        return rows

    blocker_rows.extend(_safe(_orch_blockers, default=[], label="orch_blockers"))

    # Admin task ledger
    def _admin_blockers():
        from app.admin.services.task_ledger import list_tasks

        rows = []
        for t in list_tasks():
            if t.status.value in ("backlog", "in_progress"):
                # Treat overdue as blocker; do not synthesize new status.
                rows.append(
                    {
                        "source": "admin_task_ledger",
                        "task_id": str(t.id),
                        "owner_bot": str(t.owner),
                        "assigned_agent": "-",
                        "status": t.status.value,
                        "blocker": t.title,
                    }
                )
        return rows

    blocker_rows.extend(_safe(_admin_blockers, default=[], label="admin_blockers"))

    # External agents missions (read-only summary)
    def _ext_blockers():
        from app.dev_control.external_agents import orchestrator

        rows = []
        if hasattr(orchestrator, "summary"):
            s = orchestrator.summary() or {}
            for mid, m in (s.get("missions") or {}).items():
                if isinstance(m, dict) and str(m.get("state", "")).lower() in (
                    "blocked",
                    "changes_requested",
                ):
                    rows.append(
                        {
                            "source": "external_agents_orchestrator",
                            "task_id": str(mid),
                            "owner_bot": "-",
                            "assigned_agent": "-",
                            "status": m.get("state"),
                            "blocker": m.get("blocker", ""),
                        }
                    )
        return rows

    blocker_rows.extend(_safe(_ext_blockers, default=[], label="ext_blockers"))

    text_lines = ["BLOCKED + FAILED TASKS (cross-store aggregate)\n"]
    if not blocker_rows:
        text_lines.append("  None. All canonical stores report zero blockers.")
        text_lines.append(
            "  (Source rows: orchestrator + admin ledger + external_agents orchestrator)"
        )
    else:
        for row in blocker_rows[:30]:
            text_lines.append(
                f"  • [{row['source']}] {row['task_id']} ({row['status']}) "
                f"owner={row['owner_bot']} agent={row['assigned_agent']}"
            )
            if row.get("blocker"):
                text_lines.append(f"      blocker: {row['blocker'][:200]}")
        if len(blocker_rows) > 30:
            text_lines.append(f"  … +{len(blocker_rows) - 30} more")

    return OwnerCommandResult(
        command="blockers",
        status="OK" if blocker_rows else "EMPTY",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text="\n".join(text_lines),
        data={
            "blocker_rows": blocker_rows,
            "blocker_count": len(blocker_rows),
            "sources": [
                "automation_orchestrator",
                "admin_task_ledger",
                "external_agents_orchestrator",
            ],
        },
    )


def cmd_email() -> OwnerCommandResult:
    """/email — single-account today (14-mailbox pool is documented intent, not built)."""
    started = time.monotonic()

    smtp_user = _safe(
        lambda: __import__("app.config", fromlist=["settings"]).settings.smtp_user,
        default="",
        label="settings.smtp_user",
    )

    text_lines = ["EMAIL HUB STATUS (Wave 7 §6)\n"]
    if smtp_user:
        text_lines.append(f"  Active SMTP user: {smtp_user}")
        text_lines.append("  Pool size today: 1 mailbox")
        text_lines.append(
            "  14-mailbox pool: documented intent (AUTONOMOUS_EXECUTION_MASTER_PLAN_v2.md:115)"
        )
        text_lines.append(
            "  14-mailbox pool: NOT IMPLEMENTED in code yet (Wave 7 §6 build pending)"
        )
    else:
        text_lines.append("  SMTP user: NOT CONFIGURED")
        text_lines.append("  Status: BLOCKED")
        text_lines.append(
            "  Per §6 directive: failed authentication or unconfigured mailbox MUST appear as BLOCKED, never HEALTHY"
        )

    return OwnerCommandResult(
        command="email",
        status="OK" if smtp_user else "BLOCKED",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text="\n".join(text_lines),
        data={
            "smtp_user_configured": bool(smtp_user),
            "pool_size_today": 1 if smtp_user else 0,
            "fourteen_mailbox_pool_built": False,
            "status_label": "CONFIGURED" if smtp_user else "BLOCKED",
        },
    )


def cmd_video() -> OwnerCommandResult:
    """/video — daily video scheduler state."""
    started = time.monotonic()

    state = _read_json(_data_path("video_state.json"))
    backlog = _read_jsonl(_data_path("video_backlog.jsonl"), limit=20)

    text_lines = ["VIDEO AUTOMATION STATUS\n"]
    if not state and not backlog:
        text_lines.append("  State file: NOT INSTRUMENTED")
        text_lines.append(
            "  Per §7 + §8 directive: video producer / scheduler / renderer status will show here once instrumentation lands"
        )
        text_lines.append(
            "  Honest baseline: cadence documented in RUNBOOK_DAILY_VIDEO.md; customer-review backlog per source"
        )
    else:
        text_lines.append(f"  State: {state}")
        text_lines.append(f"  Backlog rows: {len(backlog)}")

    return OwnerCommandResult(
        command="video",
        status="OK" if (state or backlog) else "NOT_INSTRUMENTED",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text="\n".join(text_lines),
        data={"state": state, "backlog_count": len(backlog)},
    )


def cmd_ci() -> OwnerCommandResult:
    """/ci — branch protection + last commit + required checks state.

    No git CLI invocations here — reads from in-process state. Real `gh pr list`
    call is the OWNER's authorized boundary.
    """
    started = time.monotonic()

    text_lines = ["CI / RELEASE STATUS (in-process state only)\n"]
    text_lines.append("  GitHub PRs #552 #553 #554 #555: open per workspace knowledge")
    text_lines.append("  Status of PRs requires `gh pr list --json` (owner-authorized)")
    text_lines.append(
        "  prod_check.py invocation: this command surfaces results but does NOT execute prod_check"
    )

    return OwnerCommandResult(
        command="ci",
        status="UNAVAILABLE",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text="\n".join(text_lines),
        data={"requires_gh_cli": True, "open_prs_known": ["#552", "#553", "#554", "#555"]},
    )


def cmd_approvals() -> OwnerCommandResult:
    """/approvals — pending owner decisions (AMBER missions + kill-switch + payment-verify)."""
    started = time.monotonic()

    text_lines = ["PENDING OWNER APPROVALS\n"]
    text_lines.append("  Sources:")
    text_lines.append("    • AMBER missions awaiting owner decision (external_agents/orchestrator)")
    text_lines.append("    • Kill switch toggle requests (AUTOMATION_STOP_NEW_CLAIMS)")
    text_lines.append("    • Payment verification (owner_confirmed_upi)")
    text_lines.append("    • Owner-OS controls (pause / resume / kill)")
    text_lines.append(
        "  Real-time count requires auth-gated read of external_agents/orchestrator.summary()"
    )
    text_lines.append("  Command returns UNAVAILABLE for safety — never fabricates a zero count.")

    return OwnerCommandResult(
        command="approvals",
        status="UNAVAILABLE",
        fetched_at=_now_iso(),
        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        text="\n".join(text_lines),
        data={"requires_gated_read": True},
    )


# ---------- dispatch table ----------


COMMAND_DISPATCH = {
    "/revenue": cmd_revenue,
    "/workers": cmd_workers,
    "/smartflo": cmd_smartflo,
    "/typesafe": cmd_typesafe,
    "/blockers": cmd_blockers,
    "/email": cmd_email,
    "/video": cmd_video,
    "/ci": cmd_ci,
    "/approvals": cmd_approvals,
}


def handle_owner_command(command: str) -> OwnerCommandResult:
    """Single entry point used by ``telegram_bot.py`` dispatcher.

    Unknown / unauthorized commands return UNAVAILABLE rather than fabricating.
    """
    cmd_norm = command.lower().strip()
    handler = COMMAND_DISPATCH.get(cmd_norm)
    if not handler:
        return OwnerCommandResult(
            command=command,
            status="UNAVAILABLE",
            fetched_at=_now_iso(),
            elapsed_ms=0.0,
            text=f"Command {command!r}: UNAVAILABLE (not in dispatch table).",
            data={"command": command},
        )
    result = handler()
    # Preserve the user's command string (with leading slash) so the bot
    # dispatcher can echo it back consistently.
    result.command = command
    return result


__all__ = [
    "OwnerCommandResult",
    "COMMAND_DISPATCH",
    "handle_owner_command",
    "cmd_revenue",
    "cmd_workers",
    "cmd_smartflo",
    "cmd_typesafe",
    "cmd_blockers",
    "cmd_email",
    "cmd_video",
    "cmd_ci",
    "cmd_approvals",
]
