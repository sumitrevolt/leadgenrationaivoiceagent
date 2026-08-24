"""Public auth endpoints must throttle brute-force / abuse (per-IP rate-limit).

Before this guard, /customer/auth/login (and signup + magic-link) had NO rate
limit, so an attacker could brute-force passwords / email-bomb magic links /
spam-create accounts. The rate_limit dep sits IN FRONT of the handler, so even
failed logins (401) count toward the budget — the Nth rapid attempt gets 429.
"""

from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_is_rate_limited():
    # 10 / 60s per IP. Fire well past the cap; a 429 MUST appear (not endless 401s).
    # Use a dedicated X-Forwarded-For so this burst lands in ITS OWN per-IP bucket
    # and never starves other tests' logins (limiter state is process-global).
    hdr = {"X-Forwarded-For": "203.0.113.77"}
    codes = [
        client.post(
            "/api/customer/auth/login",
            json={"email": "brute@example.com", "password": "wrong-guess"},
            headers=hdr,
        ).status_code
        for _ in range(16)
    ]
    assert 429 in codes, f"login endpoint not rate-limited: {codes}"
    # The limiter runs before the handler, so the early attempts are auth failures.
    assert 401 in codes, f"expected 401 auth-failures before throttle: {codes}"
