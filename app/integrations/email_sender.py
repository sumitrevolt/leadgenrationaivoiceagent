"""
Email Integration
Send notifications and reports via email
"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


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
        """
        # PREFER email API (Resend/Brevo) — SMTP se zyada reliable, koi mailbox
        # password jhanjhat nahi. Agar key set hai to API se bhejo; warna SMTP.
        try:
            from app.integrations.email_api import api_available, send_email_api

            if api_available():
                ok, info = await send_email_api(
                    to_emails, subject, body, html_body=html_body, reply_to=reply_to
                )
                if ok:
                    logger.info(f"Email sent via API ({info}) to {', '.join(to_emails)}")
                    _integ_ok("email_api")
                    return True
                logger.warning(f"Email API failed ({info}); trying SMTP fallback")
                _integ_fail("email_api", str(info))
        except Exception as e:
            logger.warning(f"Email API path error ({e}); SMTP fallback")
            _integ_fail("email_api", str(e))

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

        # Attach plain text body
        msg.attach(MIMEText(body, "plain"))

        # Attach HTML body if provided
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                use_tls=True,
            )

            logger.info(f"Email sent to {', '.join(to_emails)}")
            _integ_ok("smtp")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            _integ_fail("smtp", str(e))
            return False

    async def send_lead_alert(self, to_emails: list[str], lead_data: dict[str, Any]) -> bool:
        """Send hot lead alert email"""
        subject = f"🔥 New Hot Lead: {lead_data.get('company_name', 'Unknown')}"

        body = f"""
NEW HOT LEAD ALERT!

Company: {lead_data.get('company_name', 'N/A')}
Contact: {lead_data.get('contact_name', 'N/A')}
Phone: {lead_data.get('phone', 'N/A')}
City: {lead_data.get('city', 'N/A')}

Lead Score: {lead_data.get('lead_score', 0)}/100
Interest Level: {lead_data.get('detected_intent', 'N/A')}

Notes:
{lead_data.get('notes', 'No additional notes')}

Call Time: {lead_data.get('call_time', 'N/A')}

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
                <td style="padding: 10px;">{lead_data.get('company_name', 'N/A')}</td>
            </tr>
            <tr>
                <td style="padding: 10px; font-weight: bold;">Contact:</td>
                <td style="padding: 10px;">{lead_data.get('contact_name', 'N/A')}</td>
            </tr>
            <tr>
                <td style="padding: 10px; font-weight: bold;">Phone:</td>
                <td style="padding: 10px;"><a href="tel:{lead_data.get('phone', '')}">{lead_data.get('phone', 'N/A')}</a></td>
            </tr>
            <tr>
                <td style="padding: 10px; font-weight: bold;">City:</td>
                <td style="padding: 10px;">{lead_data.get('city', 'N/A')}</td>
            </tr>
        </table>

        <div style="background: white; padding: 15px; border-radius: 10px; margin-top: 15px;">
            <h3 style="margin-top: 0;">Lead Score: <span style="color: #667eea;">{lead_data.get('lead_score', 0)}/100</span></h3>
            <p>Interest: {lead_data.get('detected_intent', 'N/A')}</p>
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

Date: {stats.get('date', 'Today')}

CALL STATISTICS:
- Calls Made: {stats.get('calls_made', 0)}
- Connected: {stats.get('calls_connected', 0)}
- Connection Rate: {stats.get('connection_rate', 0):.1%}

OUTCOMES:
- Interested: {stats.get('interested', 0)}
- Appointments Booked: {stats.get('appointments', 0)}
- Callback Requests: {stats.get('callbacks', 0)}
- Not Interested: {stats.get('not_interested', 0)}

HOT LEADS: {stats.get('hot_leads', 0)}
ESTIMATED VALUE: ₹{stats.get('estimated_value', 0):,.0f}

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

Date: {appointment_data.get('date', 'TBD')}
Time: {appointment_data.get('time', 'TBD')}
With: {appointment_data.get('client_name', 'Our Team')}

{f"Meeting Link: {appointment_data.get('meeting_link')}" if appointment_data.get('meeting_link') else ""}

We look forward to speaking with you!

Best regards,
{appointment_data.get('client_name', 'Team')}
        """

        return await self.send_email([to_email], subject, body)
