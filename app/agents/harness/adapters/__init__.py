"""Harness adapters — thin bridges that let existing loops feed the harness.

Shadow adapters are RECORD-ONLY: they observe a legacy execution and never
execute, block, approve, retry or cancel it. See shadow.py (staff.run_member)
and dag_shadow.py (dag_engine).
"""

from app.agents.harness.adapters.batch_shadow import observe_batch_item  # noqa: F401
from app.agents.harness.adapters.coordinator_shadow import observe_coordinator_action  # noqa: F401
from app.agents.harness.adapters.dag_shadow import observe_dag_action  # noqa: F401
from app.agents.harness.adapters.shadow import (  # noqa: F401
    observe_legacy_run,
    shadow_eligible,
    shadow_loop_eligible,
)
from app.agents.harness.adapters.supervisor_shadow import observe_supervisor_action  # noqa: F401

__all__ = [
    "observe_legacy_run",
    "shadow_eligible",
    "shadow_loop_eligible",
    "observe_dag_action",
    "observe_coordinator_action",
    "observe_supervisor_action",
    "observe_batch_item",
]
