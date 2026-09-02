"""Customer 2FA TOTP API — enrol / confirm / status / disable / verify.

Mounted under /api/customer/2fa. enrol/confirm/disable require a current
customer JWT (caller proves they are the account before changing 2FA state).
verify takes the login-challenge token so it can run BEFORE the JWT exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.customer_auth import require_customer
from app.api.ratelimit import rate_limit
from app.platform import customer_totp as ct

router = APIRouter(prefix="/api/customer/2fa", tags=["Customer Auth"])


class ConfirmIn(BaseModel):
    secret: str = Field(..., min_length=16, max_length=64)
    code: str = Field(..., min_length=6, max_length=6)
    recovery_codes: list[str] = Field(..., min_length=4, max_length=16)


class DisableIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=20)


class VerifyIn(BaseModel):
    challenge_token: str = Field(..., min_length=20, max_length=2000)
    code: str = Field(..., min_length=4, max_length=20)


@router.get("/status")
async def status(client_id: str = Depends(require_customer)) -> dict:
    return {"enabled": ct.is_enabled(client_id)}


@router.post("/enroll")
async def enroll(client_id: str = Depends(require_customer)) -> dict:
    """Begin enrolment: returns secret + otpauth URI + 8 recovery codes.
    Customer must then POST /confirm with the first TOTP code AND save the
    recovery codes. Until confirm succeeds, nothing is persisted."""
    out = ct.begin_enroll(client_id, email="")
    if not out.get("ok"):
        raise HTTPException(status_code=422, detail=out.get("error", "enroll failed"))
    return out


@router.post("/confirm")
async def confirm(body: ConfirmIn, client_id: str = Depends(require_customer)) -> dict:
    out = ct.confirm_enroll(client_id, body.secret, body.code, list(body.recovery_codes))
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error", "confirm failed"))
    return out


@router.post("/disable")
async def disable(body: DisableIn, client_id: str = Depends(require_customer)) -> dict:
    out = ct.disable(client_id, body.code)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error", "disable failed"))
    return out


@router.post("/verify", dependencies=[Depends(rate_limit("cust_2fa", 10, 60))])
async def verify(body: VerifyIn) -> dict:
    """No JWT yet — the customer is between password and full token. We take
    the signed challenge issued by /api/customer/login and the TOTP code, and
    return a real JWT on success."""
    cid = ct.consume_challenge(body.challenge_token)
    if not cid:
        # Loop 21 (2026-07-10): admin observability parity with Loop 8's login_failed.
        # A single invalid challenge is boring; the ADR-064 automation-logs panel
        # filter surfaces the RATE so ops sees replay/CSRF attempts early.
        try:
            from app.platform import automation_log_service as _als

            _als.log_event(
                job_type="login_failed",
                status="failed",
                error_message="invalid_or_expired_2fa_challenge",
                triggered_by="customer_2fa_verify",
                meta_json={"stage": "challenge_consume"},
            )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="challenge invalid or expired")
    if not ct.verify(cid, body.code):
        # Loop 21: bad TOTP code — brute-force signal for admin panel. Include
        # client_id attribution (challenge was legitimately consumed) so admins
        # can spot targeted 2FA guessing on a specific account.
        try:
            from app.platform import automation_log_service as _als

            _als.log_event(
                client_id=cid,
                job_type="login_failed",
                status="failed",
                error_message="bad_2fa_code",
                triggered_by="customer_2fa_verify",
                meta_json={"stage": "totp_verify"},
            )
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="bad code")
    # Look up the email for the JWT subject
    try:
        from app.api.admin import create_access_token
        from app.api.customer_auth import _read

        rows = _read()
        email = ""
        for r in rows:
            if str(r.get("client_id")) == cid:
                email = r.get("email") or ""
                break
        token = create_access_token(cid, email or cid, "customer")
    except Exception:
        raise HTTPException(status_code=500, detail="token issue failed")
    return {"access_token": token, "token_type": "bearer", "client_id": cid}


__all__ = ["router"]
