def _task_status_value(t) -> str:
    """Return the canonical status string for a task, regardless of whether
    the store uses an enum or a string (FakeStore uses strings, real
    Orchestrator uses an enum)."""
    s = t.status
    return s.value if hasattr(s, "value") else str(s)
