"""Access tokens must carry jti+iat so admin_sessions revocation can work.

Deploy-after logout was a frontend wipe-on-first-401 bug, but the deeper gap
was that create_access_token omitted jti/iat — so logout's revoke_jti +
user-epoch bump were no-ops for issued admin JWTs.
"""

from __future__ import annotations

from jose import jwt

from app.api.admin import JWT_ALGORITHM, JWT_SECRET, create_access_token, create_refresh_token


def test_access_token_includes_jti_and_iat():
    tok = create_access_token("u-1", "a@example.com", "admin")
    claims = jwt.get_unverified_claims(tok)
    assert claims.get("type") == "access"
    assert claims.get("sub") == "u-1"
    assert claims.get("jti"), "jti required for revoke_jti on logout"
    assert claims.get("iat") is not None, "iat required for user-epoch revocation"
    # Round-trip verify with the same secret used at issue time
    verified = jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert verified["jti"] == claims["jti"]
    assert int(verified["iat"]) == int(claims["iat"])


def test_refresh_token_includes_jti_and_iat():
    tok = create_refresh_token("u-1")
    claims = jwt.get_unverified_claims(tok)
    assert claims.get("type") == "refresh"
    assert claims.get("jti")
    assert claims.get("iat") is not None


def test_successive_access_tokens_get_distinct_jti():
    a = jwt.get_unverified_claims(create_access_token("u-1", "a@example.com", "admin"))
    b = jwt.get_unverified_claims(create_access_token("u-1", "a@example.com", "admin"))
    assert a["jti"] != b["jti"]
