# Endpoint Auth

All auth flows through `app/api/auth_deps.py`. Never roll your own.

```python
from app.api.auth_deps import require_admin

@router.get("/status")
async def status(user=Depends(require_admin)): ...
```

- Admin endpoints: `Depends(require_admin)`. Customer endpoints: customer auth deps from the same module.
- JWT config comes from `app.config.settings` (pydantic-settings) — `os.environ.get()` misses `.env`-only values.
- Webhook signatures: fail-CLOSED in production.
- Every consequential admin action also writes an audit log (`log_audit` / team `log_event`), best-effort.
