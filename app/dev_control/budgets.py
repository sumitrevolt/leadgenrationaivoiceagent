"""Staged token budgets, attempt-escalation policy, and handoff packets (pure).

Complements ``service.admit_cost`` (dollar admission per call) with the
task-lifecycle discipline the operating model requires:

  * per-stage token budgets with 70% / 85% / 100% checkpoints
  * the same model gets at most TWO implementation attempts, the third must
    escalate to a stronger model class
  * repeated identical prompts are refused
  * a clean 12-field handoff packet when a worker stops (budget exhausted,
    blocked, or lease lost) so the next worker never repeats the investigation

Everything here is stdlib-pure and side-effect-free so it is trivially
unit-testable and safe to call from the runner, the API layer, or tmux tools.
"""

from __future__ import annotations

import hashlib
from typing import Any

DEFAULT_STAGE_BUDGETS: dict[str, int] = {
    "research": 8_000,
    "implementation": 30_000,
    "testing": 12_000,
    "review": 10_000,
    "final_review": 8_000,
}

CHECKPOINT_AT = 0.70  # generate a checkpoint summary
WRAP_UP_AT = 0.85  # stop expanding scope; finish tests + evidence
MAX_ATTEMPTS_PER_MODEL = 2


def total_budget(stages: dict[str, int] | None = None) -> int:
    return sum((stages or DEFAULT_STAGE_BUDGETS).values())


def budget_state(used_tokens: int, budget_tokens: int) -> dict[str, Any]:
    """Classify usage into normal / checkpoint / wrap_up / exhausted."""
    budget = max(1, int(budget_tokens))
    ratio = max(0, int(used_tokens)) / budget
    if ratio >= 1.0:
        phase, action = "exhausted", "terminate cleanly and write the handoff packet"
    elif ratio >= WRAP_UP_AT:
        phase, action = "wrap_up", "stop expanding scope; complete tests and evidence only"
    elif ratio >= CHECKPOINT_AT:
        phase, action = "checkpoint", "generate a checkpoint summary before continuing"
    else:
        phase, action = "normal", "continue"
    return {
        "phase": phase,
        "ratio": round(ratio, 4),
        "used": int(used_tokens),
        "budget": budget,
        "action": action,
    }


def attempts_by_model(attempts: list[dict[str, Any]], provider: str) -> int:
    return sum(1 for a in attempts or [] if a.get("provider") == provider and not a.get("ok"))


def next_attempt_decision(attempts: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    """Enforce the two-strikes rule: 3rd attempt must escalate, same model refused."""
    failed = attempts_by_model(attempts, provider)
    if failed >= MAX_ATTEMPTS_PER_MODEL:
        return {
            "allowed": False,
            "reason": "max_attempts_reached",
            "failed_attempts": failed,
            "required_action": "escalate_to_stronger_model",
        }
    return {"allowed": True, "failed_attempts": failed}


def prompt_fingerprint(prompt: str) -> str:
    return hashlib.sha256((prompt or "").strip().encode("utf-8", "replace")).hexdigest()


def is_repeat_prompt(previous_fingerprints: list[str], prompt: str) -> bool:
    """Identical re-prompts are prohibited -- they burn tokens without new signal."""
    return prompt_fingerprint(prompt) in set(previous_fingerprints or [])


HANDOFF_FIELDS = (
    "work_completed",
    "files_changed",
    "commands_run",
    "tests_run",
    "tests_passing",
    "tests_failing",
    "current_blocker",
    "likely_cause",
    "next_exact_action",
    "investigations_already_completed",
    "decisions_made",
    "remaining_risk",
)


def build_handoff_packet(**fields: Any) -> dict[str, Any]:
    """Validate + redact the 12-field handoff packet. Missing fields fail loudly
    so an incomplete handoff can never masquerade as a complete one."""
    missing = [f for f in HANDOFF_FIELDS if f not in fields or fields[f] in (None, "")]
    if missing:
        return {"ok": False, "reason": "missing_fields", "missing": missing}
    unknown = [k for k in fields if k not in HANDOFF_FIELDS]
    if unknown:
        return {"ok": False, "reason": "unknown_fields", "unknown": sorted(unknown)}

    from app.dev_control.context_packets import redact_packet_text

    packet = {}
    for key in HANDOFF_FIELDS:
        value = fields[key]
        if isinstance(value, (list, tuple)):
            packet[key] = [redact_packet_text(str(v)) for v in value]
        else:
            packet[key] = redact_packet_text(str(value))
    text = "\n".join(
        f"## {key.replace('_', ' ').upper()}\n"
        + ("\n".join(f"- {v}" for v in val) if isinstance(val, list) else str(val))
        for key, val in packet.items()
    )
    return {"ok": True, "packet": packet, "text": text}
