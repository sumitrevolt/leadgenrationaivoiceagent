"""Background Tasks Package

Import task modules by submodule path (`app.tasks.staff_jobs`, etc.).
Legacy re-exports for brain_training helpers stay available via lazy __getattr__
so the isolated DSH worker can import `app.tasks.dsh_jobs` without pulling the
full ML/training import graph at package import time.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "train_all_brains",
    "train_brain",
    "continuous_training_check",
    "web_knowledge_update",
    "get_training_status",
    "record_feedback",
]

_BRAIN_EXPORTS = frozenset(__all__)


def __getattr__(name: str) -> Any:
    if name in _BRAIN_EXPORTS:
        from app.tasks import brain_training

        return getattr(brain_training, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
