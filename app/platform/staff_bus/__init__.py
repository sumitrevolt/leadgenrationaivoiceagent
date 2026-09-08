"""STAFF collaboration bus — Buzz-facing projections over the 31-agent workforce.

Canonical workforce = ``team.STAFF`` (31). Comb is reviewer infrastructure, NOT
STAFF #32. Celery / Owner OS remain execution authority; this bus is the
collaboration/event plane only.

Flag: ``STAFF_BUS_ENABLED`` (default OFF / inert). Synthetic canaries may run
in-process without flipping production behaviour.
"""

from __future__ import annotations

from app.platform.staff_bus.canary import run_all_staff_canaries
from app.platform.staff_bus.envelope import EVENT_TYPES, build_envelope, validate_envelope
from app.platform.staff_bus.manifest import build_manifest, validate_manifest
from app.platform.staff_bus.runtime import StaffBus, enabled

__all__ = [
    "EVENT_TYPES",
    "StaffBus",
    "build_envelope",
    "build_manifest",
    "enabled",
    "run_all_staff_canaries",
    "validate_envelope",
    "validate_manifest",
]
