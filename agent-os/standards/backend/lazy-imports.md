# Lazy Imports in Handlers

Heavy/optional deps import INSIDE the handler so a broken downstream module can't break app import:

```python
@router.post("/crm/test")
async def crm_test(...):
    from app.platform import crm_sync
    return await crm_sync.test_connection(...)
```

⚠️ **Trade-off (2026-07-14 incident):** function-level imports dodge startup gates — `prod_check` stays green while the route 500s on request. Therefore:

- Retiring any shared helper → grep ALL its callers first (including inside function bodies).
- Every public revenue route needs a contract test that actually CALLS it.
- Weird error from an exception handler (`'_IncludedRouter' object has no attribute 'path'`) = SECONDARY; find the exception before it.
