# Error Handling

External calls NEVER crash a route. Defensive try/except + graceful degradation everywhere.

**Soft-error envelope** (validation / expected failures — return, don't raise):

```python
if not client_id:
    return {"ok": False, "error": "client_id required"}
return {"ok": True, ...}
```

**Read-side aggregators never raise** — each sub-block in its own try/except, partial data fine, top-level guard returns a safe `_defaults()` shell with unchanged shape (see `control_center.py`).

**Best-effort side-effects** (team log, notify, audit) wrapped so they can't fail the request:

```python
try:
    log_event("isha", action, detail)
except Exception:
    pass
```

**Fail direction policy:**
- fail-OPEN: billing meters, tenant middleware (never block revenue path on infra error)
- fail-CLOSED: compliance (DND lookup), webhook signatures in prod — a "fix" that weakens these is an ABORT
