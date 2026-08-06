"""PR Factory — thin Symphony-shaped dispatcher onto external_agents.

Inert unless ``PR_FACTORY_ENABLED=1`` **and** ``EXTERNAL_AGENT_ORCHESTRATOR=1``.
Never owns a second mission ledger (ADR-156).
"""

from __future__ import annotations

__all__ = ["FLAG", "factory_enabled"]

FLAG = "PR_FACTORY_ENABLED"


def factory_enabled() -> bool:
    """Dual-gate: factory flag + existing orchestrator flag. Default OFF."""
    import os

    from app.dev_control.external_agents import policy

    factory = (os.getenv(FLAG) or "0").strip().lower() in ("1", "true", "yes", "on")
    return bool(factory and policy.orchestrator_enabled())
