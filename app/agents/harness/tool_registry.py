"""
Tool registry — the real one (VA-01 / VA-02 / PM-01).

The audit found that `dev_control/registry.py` is a *model/provider* catalog,
not a *tool* catalog, and that `agent_permissions.can()` checks only the tool
*category*, never its arguments. This registry closes both gaps:

* every tool declares a Pydantic ``args_schema`` -> arguments are validated and
  bounds-checked before execution (VA-01/VA-02);
* every tool declares a ``risk`` class and an ``allowed_egress`` list -> the
  loop knows when to require approval (PM-03), checkpoint (SB-04), and how to
  scope the sandbox (SB-02);
* permission is checked **fail-closed** and delegates to the existing
  ``app.agents.agent_permissions`` when available (PM-01) instead of
  duplicating its matrix.

Registration is additive and side-effect free: importing this module registers
nothing until a tool calls ``register()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError

from .contracts import RiskClass, ToolCall

try:  # never let a logging import break the harness
    from app.utils.logger import setup_logger  # type: ignore

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover - fallback for isolated use
    import logging

    logger = logging.getLogger(__name__)


ToolFn = Callable[..., Awaitable[Any]]


@dataclass
class ToolSpec:
    name: str
    fn: ToolFn
    args_schema: type[BaseModel]
    risk: RiskClass
    # Task profiles allowed to use this tool (PM-01). Empty = any profile,
    # subject to agent_permissions.
    profiles: list[str] = field(default_factory=list)
    # Hosts the tool (and its sandbox) may reach (SB-02). Empty = no egress.
    allowed_egress: list[str] = field(default_factory=list)
    description: str = ""


class PermissionError_(Exception):
    """Raised (and caught by the loop) when a call is not permitted."""


class ToolRegistry:
    def __init__(self, permission_fn: Callable[[str, str], bool | None] | None = None) -> None:
        self._tools: dict[str, ToolSpec] = {}
        # (agent, tool) -> True/False/None(unknown). Defaults to the app's
        # agent_permissions matrix. Injectable for tests / alt deployments.
        self._permission_fn = permission_fn

    # ---- registration -------------------------------------------------
    def register(
        self,
        name: str,
        fn: ToolFn,
        args_schema: type[BaseModel],
        risk: RiskClass,
        *,
        profiles: list[str] | None = None,
        allowed_egress: list[str] | None = None,
        description: str = "",
    ) -> None:
        if name in self._tools:
            logger.warning("harness.registry: overwriting tool %s", name)
        self._tools[name] = ToolSpec(
            name=name,
            fn=fn,
            args_schema=args_schema,
            risk=risk,
            profiles=profiles or [],
            allowed_egress=allowed_egress or [],
            description=description,
        )

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    # ---- validation + permission (fail-closed) ------------------------
    def validate(self, call: ToolCall) -> BaseModel:
        """VA-01 + VA-02. Returns the parsed, bounds-checked args model or
        raises ValidationError / KeyError."""
        spec = self._tools.get(call.name)
        if spec is None:
            raise KeyError(f"unknown tool: {call.name!r}")
        # Pydantic does the schema + type + custom-validator bounds check.
        return spec.args_schema.model_validate(call.args)

    def permit(self, agent: str, profile: str, call: ToolCall) -> ToolSpec:
        """PM-01, fail-closed. Delegates to app.agents.agent_permissions when
        importable; otherwise denies unknown tools and defers to profile list."""
        spec = self._tools.get(call.name)
        if spec is None:
            raise PermissionError_(f"deny: unknown tool {call.name!r}")

        if spec.profiles and profile not in spec.profiles:
            raise PermissionError_(f"deny: profile {profile!r} not allowed for {call.name!r}")

        if self._permission_fn is not None:
            try:
                allowed = self._permission_fn(agent, call.name)
            except Exception as e:
                logger.warning("harness.registry: permission_fn errored: %s", e)
                allowed = False  # fail-closed
        else:
            allowed = self._delegate_permission(agent, call.name)
        if allowed is False:
            raise PermissionError_(f"deny: agent {agent!r} lacks permission for {call.name!r}")
        # allowed is True or None(unknown). For the harness path we treat
        # unknown as DENY for dangerous classes (fail-closed), allow for READ.
        if allowed is None and spec.risk is not RiskClass.READ:
            raise PermissionError_(f"deny (fail-closed): no explicit grant for {call.name!r}")
        return spec

    @staticmethod
    def _delegate_permission(agent: str, tool: str):
        """Returns True / False / None(unknown) from the existing matrix."""
        try:
            from app.agents import agent_permissions  # type: ignore
        except Exception:
            return None
        try:
            # can() returns bool; we cannot see "unknown", so treat a hard
            # False as deny and True as allow.
            return bool(agent_permissions.can(agent, tool))
        except Exception as e:  # never crash the pipeline
            logger.warning("harness.registry: permission check errored: %s", e)
            return False  # fail-closed


# Process-wide singleton (mirrors how dev_control keeps a module-level state).
REGISTRY = ToolRegistry()
