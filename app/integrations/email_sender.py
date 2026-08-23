"""
Email Integration
Send notifications and reports via email
"""

import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _delivery_log_meta(to_emails: list[str] | None) -> str:
    """Operational delivery evidence without recipient PII."""
    return f"recipients={len(to_emails or [])}"


def _safe_error_label(exc: BaseException) -> str:
    """Keep exception class + coarse status code; never retain provider text."""
    raw = str(exc or "")
    code = next(iter(re.findall(r"(?<!\d)([1-5]\d{2})(?!\d)", raw)), "")
    label = type(exc).__name__
    return f"{label}:code={code}" if code else label


def _safe_provider_label(info: Any) -> str:
    value = str(info or "").strip().lower()
    return value if re.fullmatch(r"[a-z0-9_]{1,32}", value) else "provider"


def _integ_fail(name: str, note: str = "") -> None:
    """integration_health counter — best-effort, KABHI raise nahi."""
    try:
        from app.platform import integration_health

        integration_health.record_failure(name, note)
    except Exception:
        pass


def _integ_ok(name: str) -> None:
    try:
        from app.platform import integration_health

        integration_health.record_success(name)
    except Exception:
        pass


class EmailSender:
    """
    Email notification sender

    Used for:
    - Lead alerts
    - Daily/weekly reports
    - Appointment confirmations
    - System notifications
    """

    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.from_email = settings.email_from or settings.smtp_user

        if self.user and self.password:
            logger.info("📧 Email Sender initialized")
        else:
            logger.warning("Email credentials not configured")

    async def send_email(
        self,
        to_emails: list[str],
        subject: str,
        body: str,
        html_body: str | None = None,
        cc: list[str] | None = None,
        reply_to: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> bool:
        """
        Send an email

        Args:
            to_emails: List of recipient emails
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            cc: CC recipients
            reply_to: Reply-to address
            extra_headers: Optional extra MIME headers (e.g. List-Unsubscribe /
                List-Unsubscribe-Post for promotional mail per RFC 2369/8058).
                Applied on the SMTP path; transactional callers pass nothing.
        """
        # PREFER email API (Resend/Brevo) — SMTP se zyada reliable, koi mailbox
        # password jhanjhat nahi. Agar key set hai to API se bhejo; warna SMTP.
        try:
            from app.integrations.email_api import api_available, send_email_api

            if api_available():
                ok, info = await send_email_api(
                    to_emails,
                    subject,
                    body,
                    html_body=html_body,
                    reply_to=reply_to,
                    extra_headers=extra_headers,  # List-Unsubscribe etc. were dropped on the API path
                )
                if ok:
                    logger.info(
                        "Email sent via API (%s; %s)",
                        _safe_provider_label(info),
                        _delivery_log_meta(to_emails),
                    )
                    _integ_ok("email_api")
                    return True
                safe_info = _safe_provider_label(info)
                logger.warning("Email API failed (%s); trying SMTP fallback", safe_info)
                _integ_fail("email_api", safe_info)
        except Exception as e:
            safe_error = _safe_error_label(e)
            logger.warning("Email API path error (%s); SMTP fallback", safe_error)
            _integ_fail("email_api", safe_error)

        if not self.user or not self.password:
            logger.warning("Email not configured (no API key + no SMTP), skipping send")
            return False

        # Create message
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_email
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject

        if cc:
            msg["Cc"] = ", ".join(cc)
        if reply_to:
            msg["Reply-To"] = reply_to

        # Extra RFC headers (e.g. List-Unsubscribe / List-Unsubscribe-Post for
        # promotional mail, RFC 2369/8058). Additive + never override core headers.
        for _hk, _hv in (extra_headers or {}).items():
            try:
                if _hk and _hv and _hk not in msg:
                    msg[_hk] = _hv
            except Exception:
                pass

        # Attach plain text body
        msg.attach(MIMEText(body, "plain"))

        # Attach HTML body if provided
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        try:
            # SMTP send ko timeout se bound karo — pehle koi timeout nahi tha, ek
            # stalled connection poora Celery task budget (600s) kha jaati thi =
            # email_outreach TimeLimitExceeded/OOM. Default 30s (EMAIL_SEND_TIMEOUT_S).
            import os as _os_smtp

            try:
                _smtp_to = float(_os_smtp.getenv("EMAIL_SEND_TIMEOUT_S", "30") or "30")
            except Exception:
                _smtp_to = 30.0
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                use_tls=True,
                timeout=_smtp_to,
            )

            logger.info("Email sent via SMTP (%s)", _delivery_log_meta(to_emails))
            _integ_ok("smtp")
            return True

        except Exception as e:
            err_str = str(e)
            safe_error = _safe_error_label(e)
            logger.error(
                "Failed to send email (%s; %s)",
                _delivery_log_meta(to_emails),
                safe_error,
            )
            _integ_fail("smtp", safe_error)
            # Account-level block (554 Disabled): re-raise so callers can fail-fast.
            if "554" in err_str or "Disabled by user" in err_str:
                # Best-effort ntfy page (additive; does NOT change fail-fast below).
                try:
                    from app.platform import ops_alerts

                    ops_alerts.maybe_alert_smtp_disabled(safe_error)
                except Exception:
                    pass
                raise
            return False

    async def send_lead_alert(self, to_emails: list[str], lead_data: dict[str, Any]) -> bool:
        """Send hot lead alert email"""
        subject = f"🔥 New Hot Lead: {lead_data.get('company_name', 'Unknown')}"

        body = f"""
NEW HOT LEAD ALERT!

Company: {lead_data.get("company_name", "N/A")}
Contact: {lead_data.get("contact_name", "N/A")}
Phone: {lead_data.get("phone", "N/A")}
City: {lead_data.get("city", "N/A")}

Lead Score: {lead_data.get("lead_score", 0)}/100
Interest Level: {lead_data.get("detected_intent", "N/A")}

Notes:
{lead_data.get("notes", "No additional notes")}

Call Time: {lead_data.get("call_time", "N/A")}

---
LeadGen AI - AI Automated Marketing + Voice Agent
        """

        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center;">
        <h1 style="color: white; margin: 0;">🔥 New Hot Lead!</h1>
    </div>

    <div style="padding: 20px; background: #f5f5f5;">
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 10px; font-weight: bold;">Company:</td>
                <td style="padding: 10px;">{lead_data.get("company_name", "N/A")}</td>
            </tr>
            <tr>
                <td style="padding: 10px; font-weight: bold;">Contact:</td>
                <td style="padding: 10px;">{lead_data.get("contact_name", "N/A")}</td>
            </tr>
            <tr>
                <td style="padding: 10px; font-weight: bold;">Phone:</td>
                <td style="padding: 10px;"><a href="tel:{lead_data.get("phone", "")}">{lead_data.get("phone", "N/A")}</a></td>
            </tr>
            <tr>
                <td style="padding: 10px; font-weight: bold;">City:</td>
                <td style="padding: 10px;">{lead_data.get("city", "N/A")}</td>
            </tr>
        </table>

        <div style="background: white; padding: 15px; border-radius: 10px; margin-top: 15px;">
            <h3 style="margin-top: 0;">Lead Score: <span style="color: #667eea;">{lead_data.get("lead_score", 0)}/100</span></h3>
            <p>Interest: {lead_data.get("detected_intent", "N/A")}</p>
        </div>
    </div>

    <div style="padding: 15px; text-align: center; color: #666; font-size: 12px;">
        LeadGen AI - AI Automated Marketing + Voice Agent
    </div>
</body>
</html>
        """

        return await self.send_email(to_emails, subject, body, html_body)

    async def send_daily_report(self, to_emails: list[str], stats: dict[str, Any]) -> bool:
        """Send daily campaign report"""
        subject = f"📊 Daily Campaign Report - {stats.get('date', 'Today')}"

        body = f"""
DAILY CAMPAIGN REPORT

Date: {stats.get("date", "Today")}

CALL STATISTICS:
- Calls Made: {stats.get("calls_made", 0)}
- Connected: {stats.get("calls_connected", 0)}
- Connection Rate: {stats.get("connection_rate", 0):.1%}

OUTCOMES:
- Interested: {stats.get("interested", 0)}
- Appointments Booked: {stats.get("appointments", 0)}
- Callback Requests: {stats.get("callbacks", 0)}
- Not Interested: {stats.get("not_interested", 0)}

HOT LEADS: {stats.get("hot_leads", 0)}
ESTIMATED VALUE: ₹{stats.get("estimated_value", 0):,.0f}

---
LeadGen AI - AI Automated Marketing + Voice Agent
        """

        return await self.send_email(to_emails, subject, body)

    async def send_appointment_confirmation(
        self, to_email: str, appointment_data: dict[str, Any]
    ) -> bool:
        """Send appointment confirmation email"""
        subject = f"Meeting Confirmed with {appointment_data.get('client_name', 'Our Team')}"

        body = f"""
Your Meeting is Confirmed!

Date: {appointment_data.get("date", "TBD")}
Time: {appointment_data.get("time", "TBD")}
With: {appointment_data.get("client_name", "Our Team")}

{f"Meeting Link: {appointment_data.get('meeting_link')}" if appointment_data.get("meeting_link") else ""}

We look forward to speaking with you!

Best regards,
{appointment_data.get("client_name", "Team")}
        """

        return await self.send_email([to_email], subject, body)


# ---------------------------------------------------------------------------
# Module-level singleton.
# Bahut saare modules (dunning, lifecycle_nurture, usage_alerts, revenue_digest,
# client_health, automation_health, telephony_readiness, gst_invoice, nps,
# client_journey, etc.) `from app.integrations.email_sender import email_sender`
# karte hain. Pehle yeh instance EXIST hi nahi karta tha -> har automated/alert
# email chup-chaap fail ho raha tha ("cannot import name 'email_sender'").
# EmailSender.__init__ sirf settings padhta hai (no network) -> import-safe.
# Defensive: kabhi raise nahi.
try:
    email_sender = EmailSender()
except Exception:  # pragma: no cover - import KABHI break nahi hona chahiye
    email_sender = None  # type: ignore[assignment]


__all__ = ["EmailSender", "email_sender"]
