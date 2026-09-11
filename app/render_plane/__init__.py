"""Render plane — the local render worker ↔ VPS data plane (pull + lease).

The VPS never dials the worker (NAT-safe, tolerates the box being asleep). The
worker polls: lease a job, heartbeat it, fetch inputs, render locally under
``network_guard``, upload the artifact, complete. Every step is idempotent so a
dropped connection or a restarted worker can never double-render or lose a job.

Submodules are exported **lazily** (PEP 562) so ``import app.render_plane`` stays
cheap and does not pull the SQLAlchemy-backed job store unless it is actually
asked for.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "RenderJob",
    "api",
    "client",
    "jobstore",
    "spool",
    "transport",
    "worker",
]

_LAZY_SUBMODULES = ("jobstore", "transport", "client", "worker", "api", "spool")


def __getattr__(name: str) -> Any:  # pragma: no cover - trivial dispatch
    if name in _LAZY_SUBMODULES:
        import importlib

        return importlib.import_module(f"app.render_plane.{name}")
    if name == "RenderJob":
        from app.render_plane.jobstore import RenderJob

        return RenderJob
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
