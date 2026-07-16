# Feature Flags

New features are env-flag-gated, **INERT by default**, additive over rewrite.

```python
def _enabled() -> bool:
    return (os.getenv("MY_FLAG", "0") or "0").strip().lower() in ("1", "true", "yes", "on")
```

- Read flags via `os.getenv` **at call-time** (not import-time) so runtime flips work.
- Unset flag = feature dormant + graceful skip, never an error.
- Register every new flag in the `AUTOMATION_FLAGS` registry.
- Automation change ships with: flag + idempotency + retry/DLQ + metrics + rollback + runbook.
