# API Router Modules

One domain = one `APIRouter` module in `app/api/`. Copy the neighbour pattern:

```python
"""Docstring header: route table + purpose (Hinglish ok)."""
from fastapi import APIRouter, Depends
from app.api.auth_deps import require_admin

router = APIRouter(prefix="/clients", tags=["Clients"])
```

- **Before adding ANY route: grep for duplicates across ALL split routers** — FastAPI is first-route-wins; a duplicate silently shadows.
- God-router splits (e.g. `growth.py` → `growth_crm.py`) mount via `parent.include_router()` with **paths unchanged**.
- Module docstring lists its routes (method + path + one-line purpose).
- New admin feature = API + UI tab together. API-only = incomplete.
- Web process never runs heavy jobs — offload to Celery.
