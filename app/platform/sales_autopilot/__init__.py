"""Autonomous Sales Engine (Sales Autopilot) — policy-driven, fail-closed, dry-run default.

An **additive, flag-gated, INERT-by-default** sales operating system. Nothing in this
package sends anything to a real provider unless ALL of the following are true:

  - ``SALES_AUTOPILOT_ENABLED=1`` (master gate), and
  - the channel gate is on (``SALES_AUTOPILOT_WHATSAPP_ENABLED`` / ``..._EMAIL_ENABLED``), and
  - the resolved policy has ``dry_run=false``, and
  - eligibility returns ELIGIBLE, and
  - the deterministic safety validator returns AUTO_APPROVED, and
  - no owner kill switch is engaged.

Any missing condition ⇒ we simulate (label ``SIMULATED``) and never touch a provider.

Calling is HARD OFF here — this engine never dials. WhatsApp uses the existing ban-safe
``whatsapp_campaign.send_one`` and never a new gateway. Follow the module docstrings.
"""

from __future__ import annotations

__all__ = [
    "policy",
    "store",
    "eligibility",
    "messages",
    "safety",
    "send",
    "followups",
    "inbound",
    "handoff",
    "scheduler",
    "refill",
    "pay_truth",
]
