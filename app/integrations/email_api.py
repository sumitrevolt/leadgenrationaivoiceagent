"""
email_api.py — API-based email sending (Resend / Brevo), SMTP se zyada reliable.
================================================================================

SMTP creds (Hostinger) flaky the → API providers (HTTPS) cleaner. Jo bhi key
.env me set hai (RESEND_API_KEY ya BREVO_API_KEY) usse bhejta hai. Dono ka free
tier hai. NEVER raises — (ok, info) tuple return karta hai.

  Resend : POST https://api.resend.com/emails        (Bearer key)
  Brevo  : POST https://api.brevo.com/v3/smtp/email   (api-key header)

api_available() batata hai koi API key set hai ya nahi (EmailSender pehle API
try karta hai, phir SMTP fallback).
"""

from __future__ import annotations

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def api_available() -> bool:
    return bool((settings.resend_api_key or "").strip() or (settings.brevo_api_key or "").strip())


def _from() -> tuple[str, str]:
    """(email, name). email_from set ho to wahi; warna resend test sender."""
    name = (settings.outreach_from_name or "LeadGen AI").strip()
    email = (settings.email_from or settings.smtp_user or "").strip()
    if not email:
        # Resend ka shared test sender (domain verify hone tak kaam karta hai)
        email = "onboarding@resend.dev"
    return email, name


async def send_email_api(
    to_emails: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    reply_to: str | None = None,
    extra_headers: dict | None = None,
) -> tuple[bool, str]:
    """Resend (priority) ya Brevo se email bhejo. (ok, info). Never raises."""
    resend = (settings.resend_api_key or "").strip()
    brevo = (settings.brevo_api_key or "").strip()
    if not (resend or brevo):
        return False, "no_api_key"

    from_email, from_name = _from()
    html = html_body or ("<p>" + (body or "").replace("\n", "<br>") + "</p>")
    try:
        import httpx
    except Exception:
        return False, "httpx_missing"

    # ---- Resend ----
    if resend:
        try:
            payload = {
                "from": f"{from_name} <{from_email}>",
                "to": to_emails,
                "subject": subject,
                "html": html,
                "text": body or "",
            }
            if reply_to:
                payload["reply_to"] = reply_to
            if extra_headers:
                payload["headers"] = dict(extra_headers)  # RFC-8058 List-Unsubscribe etc.
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {resend}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if 200 <= r.status_code < 300:
                return True, "resend"
            # Provider bodies can echo rejected recipient addresses. Status is
            # enough for operations; never retain response text in logs.
            logger.warning("[email_api] Resend status=%s", r.status_code)
            return False, f"resend_{r.status_code}"
        except Exception as e:
            logger.warning("[email_api] Resend failed: %s", type(e).__name__)
            # Brevo fallback if also set
            if not brevo:
                return False, "resend_error"

    # ---- Brevo ----
    if brevo:
        try:
            payload = {
                "sender": {"email": from_email, "name": from_name},
                "to": [{"email": e} for e in to_emails],
                "subject": subject,
                "htmlContent": html,
                "textContent": body or "",
            }
            if reply_to:
                payload["replyTo"] = {"email": reply_to}
            if extra_headers:
                payload["headers"] = dict(extra_headers)  # RFC-8058 List-Unsubscribe etc.
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "api-key": brevo,
                        "Content-Type": "application/json",
                        "accept": "application/json",
                    },
                    json=payload,
                )
            if 200 <= r.status_code < 300:
                return True, "brevo"
            logger.warning("[email_api] Brevo status=%s", r.status_code)
            return False, f"brevo_{r.status_code}"
        except Exception as e:
            logger.warning("[email_api] Brevo failed: %s", type(e).__name__)
            return False, "brevo_error"

    return False, "no_api_key"


__all__ = ["api_available", "send_email_api"]
