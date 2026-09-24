"""Fresh TypeSafe call for PR #566 vs #568 reconciliation decision.
Real API call, recorded with model + decision_id + latency + verdict.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.worktrees\fix-t80-telegram-owner-command")
sys.path.insert(0, str(ROOT))

from app.platform import typesafe_integration as ti

OUT = ROOT / "typesafe_reconcile.json"

state = {
    "task_id": "decision_pr566_vs_pr568",
    "tenant_scope": "leadgen-p0-76",
    "purpose": "canonical_pr_decision_for_task80",
    "owner_bot": "MiniMax",
    "assigned_agent": "MiniMax",
    "agent_lane": "platform",
    "priority": "HIGH",
    "pr_566_head": "d70da925",
    "pr_566_path": "fix/t80-telegram-owner-command-dispatcher",
    "pr_566_real_tests_pass": "9/9 real pytest + Ruff clean",
    "pr_566_p0_76_ack_handler": "none (uses generic /dispatch via COMMAND_DISPATCH)",
    "pr_566_type_safe_proposal": "narrow _owner_review_pre_approved per-task flag (NOT implemented)",
    "pr_568_head": "32473cdd",
    "pr_568_path": "feat/telegram-typesafe-orchestrator (or similar)",
    "pr_568_full_ci": "Gate A + security pass; full CI fail (pre-existing test_telegram_integration_2026 failure)",
    "pr_568_p0_76_ack_handler": "new app/integrations/telegram_p0_76_ack.py — binds inbound 'P0-76 ACK' to task_79406871 by idempotency key p0-76:guardian:hermes:telegram_owner_command",
    "pr_568_type_safe": "TYPESAFE_ENABLED=0 documented deterministic policy degradation (NO global override)",
    "task_79406871_state_in_real_ledger": "REVIEW with TypeSafe session policy gate reason (from prior run)",
    "vps_poller_touched": "neither PR touched VPS poller",
    "owner_directive": "Apni branch par edit karne se pehle overlap resolve kare; single #80 PR/code owner canonical ledger me decide",
    "evidence_refs": [
        "github://pull/566/commits/d70da925",
        "github://pull/568/commits/32473cdd",
        "deliverables/telegram-p0-20260923/T80_P0_76_FINAL_REPORT.md",
        "orchestrator_ledger://task_79406871",
    ],
}

print("LIVE_TYPESAFE_CALL_START", flush=True)
t0 = time.time()
try:
    resp = ti.get_typesafe_client().system_one(state, {
        "route": ti.Choice(
            "Which PR is the canonical Task #80 implementation for production deployment?",
            state,
            [
                "pr_566_only_close_568",
                "pr_568_only_close_566",
                "merge_both_close_neither",
                "escalate_to_agnes_owner",
            ],
        ),
        "reason": ti.Noul(
            "In one sentence, which choice minimizes production-deploy risk?",
            state,
        ),
    })
    latency = time.time() - t0

    payload = {
        "decision_id": getattr(resp, "decision_id", None),
        "model_resolved": getattr(resp, "model", "unknown"),
        "latency_sec": round(latency, 3),
        "answer_route": resp.answers.get("route") if hasattr(resp, "answers") else None,
        "answer_reason": resp.answers.get("reason") if hasattr(resp, "answers") else None,
        "confidence_basis": resp.answers.get("confidence_basis") if hasattr(resp, "answers") else None,
        "answers_full": {k: getattr(v, "value", str(v)) for k, v in (resp.answers or {}).items()} if hasattr(resp, "answers") else None,
    }
except Exception as e:
    latency = time.time() - t0
    payload = {
        "decision_id": None,
        "latency_sec": round(latency, 3),
        "error_type": type(e).__name__,
        "error": str(e),
        "note": "TypeSafe API failed — falling back to engineer judgment below",
    }

payload["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
payload["credential_state"] = ti.credential_state()
payload["script_path"] = str(OUT)

OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
print(f"LIVE_TYPESAFE_CALL_DONE latency_sec={payload['latency_sec']} wrote={OUT}")
print(json.dumps(payload, indent=2, default=str))
