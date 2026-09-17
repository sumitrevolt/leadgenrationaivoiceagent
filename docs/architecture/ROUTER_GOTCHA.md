# ROUTER GOTCHA — FastAPI `Depends` lives in `route.dependant.dependencies`

> **Owner:** M5 (see `deliverables/software-company/crore-strategy-ARCH-2026-09-16.md` §M5)
> **Evidence label:** `CODE-PRESENT` (verified against FastAPI's `APIRoute` internals).

## The gotcha

A FastAPI route declared with a **signature-level** dependency:

```python
@router.get("/thing")
async def get_thing(_admin = Depends(require_admin)):
    ...
```

does **NOT** put the dependency in `route.dependencies`.

* `route.dependencies` → only deps passed via the **decorator**, e.g.
  `@router.get("/x", dependencies=[Depends(require_admin)])`.
* `route.dependant.dependencies` → the **signature-level** `Depends(...)` args
  (this is where `Depends(require_admin)` in the function signature lands).

## Why this matters here

Any code or test that verifies "is this route gated?" by inspecting
`route.dependencies` will **silently see an empty list** for a signature-gated route
and wrongly conclude the route is **ungated**. That is a security-relevant false
negative.

## The rule

When asserting a route is gated, walk **both**:

```python
from fastapi.routing import APIRoute

def is_gated(route: APIRoute, guard) -> bool:
    # decorator-level deps
    if any(d.call is guard for d in route.dependencies):
        return True
    # signature-level deps (where the gotcha bites)
    return any(d.call is guard for d in route.dependant.dependencies)
```

## Our convention (crore-strategy T05)

* New gated routes use a **real signature dependency**: `_admin = Depends(require_admin)`.
* Routes added in this work: `app/api/kpi_honest_view.py`, `app/api/owner_revenue_kit.py`
  — all admin-gated via signature `Depends(require_admin)`.
* Tests that pin gating (`tests/test_kpi_ledger.py`) check `route.dependant.dependencies`,
  not just `route.dependencies`.

## Verified gated routes in this stage

| Route | Module | Guard | Location |
|---|---|---|---|
| `GET /app/kpi/honest` | `app/api/kpi_honest_view.py` | `require_admin` | `dependant.dependencies` |
| `GET /app/kpi/dev-workers` | `app/api/kpi_honest_view.py` | `require_admin` | `dependant.dependencies` |
| `GET /app/revenue-kit/summary` | `app/api/owner_revenue_kit.py` | `require_admin` | `dependant.dependencies` |
| `GET /app/revenue-kit/pending` | `app/api/owner_revenue_kit.py` | `require_admin` | `dependant.dependencies` |
| `POST /app/revenue-kit/confirm/{payment_id}` | `app/api/owner_revenue_kit.py` | `require_admin` | `dependant.dependencies` |
