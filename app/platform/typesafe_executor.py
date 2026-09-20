"""
TypeSafe Execution Layer — Output Validation & Worker Coordination (2026-09-19)

Connects the existing TypeSafe integration to actual worker execution and
output quality validation. Not just decisions — actual deliverables.

Architecture:
  1. Load canonical skills + project context
  2. TypeSafe JEv intelligence for task selection/quality criteria
  3. OmniRoute + execution agents generate content/code/deliverables
  4. Output verification via TypeSafe judgments + factual checks
  5. Actual delivery + feedback tracking

Gap being filled: workers.py defines skill schemas but has NO execution
or validation logic. TypeSafe is called in agent_talent_pool.py but
outputs aren't validated against real deliverables. This module bridges
that gap with bounded revision loops and measured outcomes.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.platform.typesafe_integration import (
    Choice,
    Noul,
    Score,
    TypeSafeClient,
    TypeSafeResponse,
    get_typesafe_client,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Execution result taxonomy
# --------------------------------------------------------------------------- #


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    VALIDATING = "validating"
    REVISING = "revising"  # TypeSafe rejected, bounded retry
    DELIVERED = "delivered"  # Verified output passed to customer/system
    FAILED = "failed"  # Exhausted revision budget or hard fail
    INERT = "inert"  # TypeSafe unavailable, deterministic fallback


@dataclass
class ExecutionResult:
    """Result of a worker task execution with TypeSafe validation."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    worker_id: str = ""
    skill_name: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING

    # Input
    input_data: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    # Output
    output: dict[str, Any] | None = None
    deliverable: Any = None  # Actual artifact (email body, code diff, etc.)

    # Validation
    typesafe_verdict: TypeSafeResponse | None = None
    revision_count: int = 0
    max_revisions: int = 3
    validation_criteria: dict[str, Any] = field(default_factory=dict)

    # Evidence
    latency_sec: float = 0.0
    attempts: list[dict[str, Any]] = field(default_factory=list)
    downstream_effect: dict[str, Any] = field(default_factory=dict)

    # Measurable outcome (filled by worker after delivery)
    outcome: dict[str, Any] = field(default_factory=dict)
    # e.g., {"email_sent": True, "message_id": "abc", "reply_received": False}
    # e.g., {"pr_merged": True, "ci_passed": True, "deployed_sha": "deadbeef"}

    @property
    def is_delivered(self) -> bool:
        return self.status == ExecutionStatus.DELIVERED

    @property
    def needs_revision(self) -> bool:
        return self.status == ExecutionStatus.REVISING and self.revision_count < self.max_revisions


# --------------------------------------------------------------------------- #
# TypeSafe Executor — common judgment + validation interface
# --------------------------------------------------------------------------- #


class TypeSafeExecutor:
    """Common execution + validation interface for workers and agents.

    Reuses the existing TypeSafeClient (System One API). Adds:
    - Output quality validation (not just decision validation)
    - Bounded revision loops (TypeSafe rejects → targeted correction)
    - Measurable outcome tracking
    - Deterministic fallback when TypeSafe is INERT
    """

    def __init__(self, client: TypeSafeClient | None = None):
        self.client = client or get_typesafe_client()

    # ------------------------------------------------------------------- #
    # Core: validate an output artifact against quality criteria
    # ------------------------------------------------------------------- #

    def validate_output(
        self,
        artifact: dict[str, Any],
        criteria: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> TypeSafeResponse:
        """Validate a deliverable against TypeSafe quality criteria.

        Example:
            artifact = {"subject": "Your free audit is ready", "body": "..."}
            criteria = {"tone": "professional", "length": "< 200 words",
                        "cta": "present", "spam_score": "low"}
        """
        state = {
            "artifact": artifact,
            "criteria": criteria,
            "context": context or {},
        }
        questions = {
            "quality": Score(
                "Rate the quality of this deliverable against the criteria",
                criteria=["poor", "adequate", "good", "excellent"],
            ),
            "compliant": Noul("Does this deliverable meet ALL specified criteria?"),
        }
        return self.client.system_one(state, questions)

    # ------------------------------------------------------------------- #
    # Core: judge task routing / next action
    # ------------------------------------------------------------------- #

    def select_action(
        self,
        task_description: str,
        available_actions: dict[str, str],
        context: dict[str, Any] | None = None,
    ) -> TypeSafeResponse:
        """Pick the next best action from available options."""
        state = {
            "task": task_description,
            "context": context or {},
        }
        questions = {
            "action": Choice(task_description, available_actions),
        }
        return self.client.system_one(state, questions)

    # ------------------------------------------------------------------- #
    # Core: revise a rejected artifact (bounded correction)
    # ------------------------------------------------------------------- #

    def revise_artifact(
        self,
        artifact: dict[str, Any],
        rejection_reason: str,
        criteria: dict[str, Any],
    ) -> TypeSafeResponse:
        """Targeted correction instruction for a rejected deliverable."""
        state = {
            "artifact": artifact,
            "rejection_reason": rejection_reason,
            "criteria": criteria,
        }
        questions = {
            "correction": Choice(
                "What specific change would fix this deliverable?",
                {
                    "tone_adjust": "Adjust tone to match brand voice",
                    "length_fix": "Shorten or lengthen to meet criteria",
                    "cta_add": "Add or improve the call-to-action",
                    "personalize": "Add personalization tokens",
                    "compliance_fix": "Fix compliance/DND/TRAI issue",
                },
            ),
        }
        return self.client.system_one(state, questions)

    # ------------------------------------------------------------------- #
    # High-level: execute + validate + deliver with bounded revision
    # ------------------------------------------------------------------- #

    def execute_and_validate(
        self,
        worker_id: str,
        skill_name: str,
        input_data: dict[str, Any],
        deliver_fn,  # callable(input_data) -> artifact
        validate_criteria: dict[str, Any],
        context: dict[str, Any] | None = None,
        max_revisions: int = 3,
    ) -> ExecutionResult:
        """Execute a worker task, validate output, revise if rejected.

        This is the canonical flow:
          1. deliver_fn(input_data) → artifact
          2. validate_output(artifact, criteria) → TypeSafe verdict
          3. If rejected AND budget remains → revise → re-validate
          4. Return ExecutionResult with DELIVERED or FAILED status

        `deliver_fn` is the actual work: send_email, generate_code, etc.
        It must be deterministic given the same input (no TypeSafe calls inside).
        """
        result = ExecutionResult(
            worker_id=worker_id,
            skill_name=skill_name,
            input_data=input_data,
            context=context or {},
            validation_criteria=validate_criteria,
            max_revisions=max_revisions,
        )
        result.status = ExecutionStatus.RUNNING

        for attempt in range(max_revisions + 1):
            result.revision_count = attempt
            start = time.time()

            try:
                # Step 1: Produce the deliverable
                artifact = deliver_fn(input_data)
                result.output = artifact
                result.latency_sec = time.time() - start

            except Exception as e:
                result.status = ExecutionStatus.FAILED
                result.attempts.append(
                    {
                        "attempt": attempt,
                        "phase": "deliver",
                        "error": str(e),
                    }
                )
                logger.error(f"[{worker_id}] deliver_fn failed: {e}")
                return result

            # Step 2: TypeSafe unavailable → deterministic pass (fail-open)
            if not self.client.enabled:
                result.status = ExecutionStatus.INERT
                result.typesafe_verdict = TypeSafeResponse(
                    success=False,
                    error="INERT: no API key",
                )
                return result

            # Step 3: Validate against criteria
            result.status = ExecutionStatus.VALIDATING
            verdict = self.validate_output(artifact, validate_criteria, context)
            result.typesafe_verdict = verdict
            result.attempts.append(
                {
                    "attempt": attempt,
                    "phase": "validate",
                    "success": verdict.success,
                    "value": verdict.value if verdict.success else verdict.error,
                }
            )

            if not verdict.success:
                # TypeSafe call itself failed → don't block on infra gap
                logger.warning(f"[{worker_id}] TypeSafe validation failed: {verdict.error}")
                result.status = ExecutionStatus.INERT
                return result

            # Step 4: Check the verdict
            answers = verdict.answers
            quality = answers.get("quality", {})
            compliant = answers.get("compliant", {})

            # Wire format for Noul is {"type": "noul", "noul": float} (probability of YES)
            noul_val = compliant.get("noul")
            if isinstance(noul_val, bool):
                noul_prob = 1.0 if noul_val else 0.0
            elif isinstance(noul_val, (int, float)):
                noul_prob = float(noul_val)
            else:
                noul_prob = 0.0

            # Wire format for Score may be {"type": "score", "score": float} or choice string
            quality_choice = quality.get("choice") or quality.get("value")
            score_val = quality.get("score")
            score_num = float(score_val) if isinstance(score_val, (int, float)) else None

            is_compliant = (
                noul_prob >= 0.7
                or quality_choice in ("good", "excellent")
                or (score_num is not None and score_num >= 2.0)
            )

            if is_compliant:
                result.status = ExecutionStatus.DELIVERED
                return result

            # Step 5: Revision budget exhausted?
            if attempt >= max_revisions:
                result.status = ExecutionStatus.FAILED
                logger.warning(
                    f"[{worker_id}] Exhausted {max_revisions} revisions for {skill_name}"
                )
                return result

            # Step 6: Ask TypeSafe what to fix, then loop
            result.status = ExecutionStatus.REVISING
            rejection = f"quality={quality_choice or score_num}, compliant_prob={noul_prob}"
            revision = self.revise_artifact(artifact, rejection, validate_criteria)
            if revision.success:
                # Apply revision hint to input_data for next iteration
                correction = revision.value
                if correction:
                    input_data = dict(input_data)
                    input_data["_revision_hint"] = correction
                    logger.info(f"[{worker_id}] Revision hint: {correction}")

        return result


# --------------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------------- #

_executor: TypeSafeExecutor | None = None


def get_executor() -> TypeSafeExecutor:
    global _executor
    if _executor is None:
        _executor = TypeSafeExecutor()
    return _executor


# --------------------------------------------------------------------------- #
# Convenience: validate an artifact (module-level shortcut)
# --------------------------------------------------------------------------- #


def validate_artifact(
    artifact: dict[str, Any],
    criteria: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> TypeSafeResponse:
    """Shortcut: validate a single artifact without the full execute loop."""
    return get_executor().validate_output(artifact, criteria, context)
