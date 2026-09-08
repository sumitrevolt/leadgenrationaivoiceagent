"""adminAuthBoot must not wipe tokens on the first /api/admin/me 401.

Deploy recreate races return a transient 401 while the new container is
warming; wiping localStorage on that first 401 was the root cause of
\"deploy ke baad admin logout\" (JWT secret is stable across recreate).
"""

from __future__ import annotations

from pathlib import Path

HTML = Path("frontend/admin_dashboard.html").read_text(encoding="utf-8")


def _boot_fn() -> str:
    start = HTML.index("async function adminAuthBoot()")
    end = HTML.index("async function adminLogout()", start)
    return HTML[start:end]


def test_admin_auth_boot_retries_before_token_wipe():
    body = _boot_fn()
    assert "setTimeout" in body, "must delay before second /me probe"
    assert body.count('removeItem("accessToken")') == 1
    assert body.count("fetchMe()") >= 2 or body.count("/api/admin/me") >= 2
    # First 401 must not be the only wipe path — retry sits between
    first_401 = body.index("r.status === 401")
    wipe = body.index('removeItem("accessToken")')
    assert first_401 < wipe
    assert "1500" in body or "setTimeout" in body[first_401:wipe]


def test_admin_auth_boot_keeps_token_on_non_401_errors():
    body = _boot_fn()
    compact = body.replace(" ", "")
    assert "if(!r.ok)return" in compact
    assert "token kept" in body.lower() or "fail-open" in body.lower()
