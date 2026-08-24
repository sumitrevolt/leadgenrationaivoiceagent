"""Security tests must exercise REAL auth — not the mocked-open test harness.

The top-level `tests/conftest.py` overrides every auth dependency
(`require_admin` / `require_super_admin` / `require_agent` / `require_manager` /
`get_current_user`) with a mock SUPER_ADMIN user so the rest of the suite can
reach protected endpoints without juggling tokens.

For the SECURITY suite that override is fatal: every request would arrive
pre-authenticated as super-admin, so "unauthenticated request must be rejected"
assertions would be meaningless — a `require_admin` endpoint would return 200 to
an anonymous caller and the test would (correctly, but uselessly) flag a bypass
that only exists because the harness mocked auth open.

This package-scoped, autouse fixture REMOVES those auth overrides for the
duration of each security test so real 401/403 enforcement is verified, then
restores them. DB overrides (test DB) are intentionally left in place.
"""

from __future__ import annotations

import pytest

from app.api.auth_deps import (
    get_current_user,
    require_admin,
    require_agent,
    require_manager,
    require_super_admin,
)
from app.main import app

_AUTH_DEPS = (
    get_current_user,
    require_admin,
    require_agent,
    require_manager,
    require_super_admin,
)


@pytest.fixture(autouse=True)
def _real_auth_enforcement():
    """Strip the harness's mock-admin auth overrides so auth is tested for real."""
    saved = {d: app.dependency_overrides[d] for d in _AUTH_DEPS if d in app.dependency_overrides}
    for d in _AUTH_DEPS:
        app.dependency_overrides.pop(d, None)
    try:
        yield
    finally:
        app.dependency_overrides.update(saved)
