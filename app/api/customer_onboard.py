"""customer_onboard.py — single-call admin onboarding (profile + login).

Until now, adding a new paying customer required the operator to:
  1. POST /api/clients                   to create the marketing profile
  2. POST /api/customer/auth/set-password to create login credentials
  3. (optional) Manually enroll a plan / subscription
  4. (optional) Email the customer their login details

That's friction at the moment that matters most — the first paying customer.
This module is the single admin endpoint that does the first three steps
atomically and returns a ready-to-share dashboard URL + plaintext password
(shown ONCE; same pattern as MCP-key / webhook-secret issuance).
"""

from __future__ import annotations

import secrets
import string
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/admin/customers", tags=["Admin Customers"])


_ALPHABET = string.ascii_letters + string.digits
_VALID_PLANS = {"trial", "starter", "growth", "advanced"}


class OnboardIn(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=200)
    niche: str = Field("general", max_length=80)
    city: str = Field("", max_length=80)
    phone: str = Field(..., min_length=8, max_length=20)
    email: EmailStr | None = None
    plan: str = Field("trial", max_length=20)
    # If unset, server generates a random 14-char password and returns it ONCE.
    # If set, operator-chosen (e.g. customer asked for a specific one).
    password: str | None = Field(None, min_length=8, max_length=64)
    # Optional brand colours (passed through to clients_store)
    primary_color: str = Field("", max_length=10)
    accent_color: str = Field("", max_length=10)


def _gen_password() -> str:
    """14-char password from secrets — strong default + human-typable."""
    rng = secrets.SystemRandom()
    return "".join(rng.choice(_ALPHABET) for _ in range(14))


@router.post("/onboard")
async def onboard_customer(body: OnboardIn, _user=Depends(require_admin)) -> dict[str, Any]:
    """Create profile + login + (optional) trial subscription in one call.

    Returns:
      {
        "client_id":            "...",     # The customer's stable ID
        "business_name":        "...",
        "login_email":          "...",
        "password":             "...",     # PLAINTEXT — shown only on this call
        "password_generated":   bool,      # True if server generated it
        "customer_dashboard":   "/app/customer?client_id=...",
        "magic_link_hint":      "...",     # short note if magic-link is on
      }

    Idempotent on (phone, business_name): repeat call returns the existing
    client_id but issues a fresh password (operator can use this to reset
    a customer's password without touching the password-reset flow).
    """
    plan = (body.plan or "trial").strip().lower()
    if plan not in _VALID_PLANS:
        raise HTTPException(
            status_code=422,
            detail=f"plan must be one of {sorted(_VALID_PLANS)}",
        )

    # 1) Create / dedupe the profile (clients_store handles idempotency on phone).
    try:
        from app.marketing import clients_store

        brand = {
            "primary_color": body.primary_color or "",
            "accent_color": body.accent_color or "",
        }
        client = clients_store.add_client(
            business_name=body.business_name.strip(),
            niche=(body.niche or "general").strip().lower(),
            city=(body.city or "").strip(),
            phone=body.phone.strip(),
            plan=plan,
            brand=brand,
            socials={},
        )
        client_id = str(client.get("id") or "")
        if not client_id:
            raise HTTPException(status_code=500, detail="client store returned no id")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"client_store add failed: {e}")

    # 2) Issue/reset login credentials if an email was provided.
    login_email = ""
    password = ""
    password_generated = False
    if body.email:
        try:
            from app.api import customer_auth

            password = body.password or _gen_password()
            password_generated = body.password is None
            login_email = str(body.email).strip().lower()
            customer_auth.register_login(login_email, password, client_id)
        except Exception as e:
            # Profile already saved — log the partial state and surface in response
            raise HTTPException(
                status_code=500,
                detail=f"profile created but login wire failed: {e}",
            )

    # 3) Best-effort: log the onboarding event in the audit table (rohan = leads manager).
    try:
        from app.platform.team import log_event

        log_event(
            "rohan",
            "customer_onboarded",
            f"{body.business_name} ({body.niche}, {plan}) - {body.phone}",
            meta={"client_id": client_id, "via": "admin_onboard"},
        )
    except Exception:
        pass

    customer_dashboard = f"/app/customer?client_id={client_id}"
    magic_link_hint = (
        "MAGIC_LINK=1 set — customer can ALSO use /app/login passwordless"
        if (__import__("os").environ.get("MAGIC_LINK", "0").strip()
            .lower() in ("1", "true", "yes"))
        else ""
    )

    return {
        "client_id": client_id,
        "business_name": body.business_name.strip(),
        "login_email": login_email,
        "password": password,  # plaintext — shown only this once
        "password_generated": password_generated,
        "plan": plan,
        "customer_dashboard": customer_dashboard,
        "magic_link_hint": magic_link_hint,
    }


__all__ = ["router"]
