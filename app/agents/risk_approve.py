"""Risk-scored auto-approve — OpenCode/Hermes spirit. LOW-risk self-improve actions skip
the human approval gate by policy; risky ones still queue. Wired into
`self_improve.ApprovalQueue.queue_task` (gated RISK_AUTO_APPROVE, default OFF = every
queued task waits for a human, i.e. zero behaviour change).

Heuristic risk score 0.0 (safe) .. 1.0 (risky). Fail-safe: any uncertainty → risky →
NOT auto-approved. Ban-risk actions (send/call/whatsapp/pay/publish/delete) push the score
up so they keep needing a human.

Flags: RISK_AUTO_APPROVE=1 · RISK_AUTO_APPROVE_MAX_COST (₹, default 5) · threshold 0.5
"""

from __future__ import annotations

import os

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Actions whose nature is inherently higher-risk (bias the score up).
_HIGH_RISK_ACTIONS = {"code_scan", "sales_deepdive", "social_drafts", "channel_experiments"}
# Words in the reason that imply an outward/irreversible side-effect (ban-risk).
_RISK_WORDS = ("send", "call", "whatsapp", "publish", "delete", "pay", "post", "broadcast")


def enabled() -> bool:
    return (os.getenv("RISK_AUTO_APPROVE") or "").strip().lower() in ("1", "true", "yes")


def _max_cost() -> float:
    try:
        return float(os.getenv("RISK_AUTO_APPROVE_MAX_COST", "5") or 5)
    except Exception:
        return 5.0


def score(task_name: str, cost_estimate: float = 0.0, reason: str = "") -> float:
    """0.0 safe .. 1.0 risky. Never raises (unknown → 1.0 = risky)."""
    try:
        s = 0.0
        if (task_name or "") in _HIGH_RISK_ACTIONS:
            s += 0.6
        c = max(0.0, float(cost_estimate or 0.0))
        s += min(0.4, (c / max(1.0, _max_cost())) * 0.4)
        txt = (reason or "").lower()
        if any(w in txt for w in _RISK_WORDS):
            s += 0.3
        return max(0.0, min(1.0, s))
    except Exception:
        return 1.0


def should_auto_approve(task_name: str, cost_estimate: float = 0.0, reason: str = "") -> bool:
    """True only for clearly low-risk + cheap actions. Never raises (default False)."""
    try:
        if float(cost_estimate or 0.0) > _max_cost():
            return False
        return score(task_name, cost_estimate, reason) < 0.5
    except Exception:
        return False


__all__ = ["enabled", "score", "should_auto_approve"]
