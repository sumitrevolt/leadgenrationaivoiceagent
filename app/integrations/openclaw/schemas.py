"""Pydantic / typed dict schemas for Owner Copilot API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CopilotCommandIn(BaseModel):
    """Typed Owner Copilot command request."""

    command: str = Field(..., min_length=3, max_length=80)
    params: dict[str, Any] = Field(default_factory=dict)
    text: str | None = Field(
        None,
        max_length=2000,
        description="Optional natural-language original; never executed directly",
    )
    idempotency_key: str | None = Field(None, max_length=80)
    confirm: bool = False
    correlation_id: str | None = Field(None, max_length=80)


class CopilotNlIn(BaseModel):
    """Natural language → typed proposal (preview or execute)."""

    text: str = Field(..., min_length=3, max_length=2000)
    execute: bool = False
    confirm: bool = False
    idempotency_key: str | None = Field(None, max_length=80)


class ApprovalDecisionIn(BaseModel):
    decision: str = Field(..., min_length=6, max_length=32)  # approve / reject
    reason: str = Field("", max_length=200)
    idempotency_key: str | None = Field(None, max_length=80)


class CopilotCommandResult(BaseModel):
    ok: bool
    command: str
    command_id: str | None = None
    correlation_id: str | None = None
    safety_lane: str
    status: str
    approval_required: bool = False
    approval_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    evidence: dict[str, Any] | None = None
    deduped: bool = False
    verified: bool = False
    next_action: str | None = None
