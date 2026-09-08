"""Loop 16 (2026-07-10): shared rate_limit dep returns structured 429.

Every endpoint using `Depends(rate_limit(...))` or `Depends(tier_rate_limit(...))`
should return the same detail schema Loop 6 established: `{error, message,
retry_after, scope}` plus a standards-compliant `Retry-After` header. Any FE can
then render a countdown across signup / login / any protected endpoint.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_rate_limit_dep_returns_structured_detail():
    """Directly exercise the dep — assert the HTTPException detail shape."""
    from fastapi import HTTPException

    from app.api.ratelimit import rate_limit

    dep = rate_limit("test_bucket_a", max_requests=1, window_seconds=42)

    class _Req:
        headers = {"x-forwarded-for": "9.9.9.9"}

        class client:
            host = "9.9.9.9"

    # First call passes; second trips the limit.
    await dep(_Req())
    with pytest.raises(HTTPException) as ex:
        await dep(_Req())
    assert ex.value.status_code == 429
    detail = ex.value.detail
    assert isinstance(detail, dict), f"detail must be a dict, got {type(detail).__name__}"
    assert detail["error"] == "rate_limited"
    assert detail["scope"] == "test_bucket_a"
    assert detail["retry_after"] == 42
    assert "message" in detail
    assert (ex.value.headers or {}).get("Retry-After") == "42"


@pytest.mark.asyncio
async def test_tier_rate_limit_dep_returns_structured_detail_with_tier():
    """tier_rate_limit MUST additionally include the resolved `tier`."""
    from fastapi import HTTPException

    from app.api.ratelimit import tier_rate_limit

    dep = tier_rate_limit("test_bucket_b", base_max=1, window_seconds=15)

    class _Req:
        headers = {"x-forwarded-for": "8.8.8.8"}

        class client:
            host = "8.8.8.8"

        class state:
            tenant = None  # -> free tier default

    await dep(_Req())
    with pytest.raises(HTTPException) as ex:
        await dep(_Req())
    assert ex.value.status_code == 429
    detail = ex.value.detail
    assert isinstance(detail, dict)
    assert detail["error"] == "rate_limited"
    assert detail["scope"] == "test_bucket_b"
    assert detail["retry_after"] == 15
    assert detail["tier"] == "free"
    assert (ex.value.headers or {}).get("Retry-After") == "15"
