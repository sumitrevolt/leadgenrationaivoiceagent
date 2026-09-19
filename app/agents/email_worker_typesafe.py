"""
Reference: TypeSafe-Integrated Email Worker (2026-09-19).

Shows how an existing worker (EmailSpecialistWorker) connects to the
TypeSafeExecutor for output validation and bounded revision.

This is a REFERENCE implementation — demonstrates the pattern.
To activate: integrate into workers.py EmailSpecialistWorker or use
as a mixin/base class.
"""

from __future__ import annotations

import logging
from typing import Any

from app.platform.typesafe_executor import ExecutionResult, get_executor

logger = logging.getLogger(__name__)


def send_cold_email_with_validation(
    recipient: str,
    template: str,
    context: dict[str, Any] | None = None,
) -> ExecutionResult:
    """Send a cold email with TypeSafe quality validation.

    Pattern:
        1. Generate email content (deterministic function)
        2. TypeSafe validates against criteria
        3. If rejected → revise → re-validate (bounded)
        4. If accepted → send via Brevo/SMTP
        5. Track outcome (sent, message_id, reply)
    """
    executor = get_executor()

    # Criteria for a good cold email
    criteria = {
        "tone": "professional yet warm",
        "length": "50-150 words",
        "personalization": "contains recipient name or business reference",
        "cta": "clear single call-to-action",
        "spam_score": "low (no excessive caps, no spam triggers)",
        "compliance": "includes unsubscribe + business address",
    }

    # Deterministic deliver function (no TypeSafe calls inside)
    def deliver_fn(input_data: dict[str, Any]) -> dict[str, Any]:
        """Generate email content."""
        # Apply revision hint if present
        hint = input_data.get("_revision_hint", "")
        tone_adjust = "tone_adjust" in hint
        personalize = "personalize" in hint

        subject = f"{context.get('recipient_name', 'Partner')} — {context.get('value_prop', 'grow your business')}"
        body = f"""Hi {context.get('recipient_name', 'there')},

I noticed {context.get('business_name', 'your business')} in {context.get('location', 'your area')}.

{context.get('hook', 'We help local businesses get more customers through automated marketing.')}

{context.get('cta', 'Worth a quick call this week?')}

Best,
{context.get('sender_name', 'Sumit')}
{context.get('sender_title', 'LeadsGenAI')}
{context.get('unsubscribe', 'Unsubscribe: reply STOP')}

{('-- Focus on warmer tone' if tone_adjust else '')}
{('-- Add specific personalization' if personalize else '')}
"""
        return {"subject": subject, "body": body, "to": recipient}

    # Execute with validation + bounded revision
    result = executor.execute_and_validate(
        worker_id="worker_email",
        skill_name="send_cold_email",
        input_data={"recipient": recipient, "template": template},
        deliver_fn=deliver_fn,
        validate_criteria=criteria,
        context=context,
        max_revisions=2,
    )

    # If delivered, actually send the email
    if result.is_delivered and result.output:
        outcome = _send_via_brevo(result.output)
        result.outcome = outcome
        result.downstream_effect = {"message_id": outcome.get("message_id")}

    return result


def _send_via_brevo(email: dict[str, Any]) -> dict[str, Any]:
    """Actually send the email via Brevo API."""
    import os

    import requests

    api_key = os.getenv("BREVO_API_KEY", "")
    if not api_key:
        logger.warning("BREVO_API_KEY not set — email NOT sent")
        return {"sent": False, "reason": "no_api_key"}

    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender": {"email": "admin@leadsgenai.in", "name": "LeadsGenAI"},
                "to": [{"email": email["to"]}],
                "subject": email["subject"],
                "htmlContent": email["body"].replace("\n", "<br>"),
            },
            timeout=15,
        )
        return {
            "sent": resp.status_code == 201,
            "message_id": resp.json().get("messageId") if resp.content else None,
            "status_code": resp.status_code,
        }
    except Exception as e:
        logger.error(f"Brevo send failed: {e}")
        return {"sent": False, "reason": str(e)}
