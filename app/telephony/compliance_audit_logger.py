"""
Compliance Audit Logging Helper
CRITICAL: Logs every compliance decision to database for TRAI/DPDP audit trail.
P0-4 Fix: Persistent audit logging required for 90-day regulatory proof.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance_audit import ComplianceAuditLog
from app.models.compliance_audit import ComplianceDecision as ComplianceDecisionEnum
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def log_compliance_decision(
    db: AsyncSession | None,
    phone: str,
    call_type: str,
    decision_allowed: bool,
    decision_reason: str,
    dnd_checked: bool = False,
    dnd_result: str | None = None,
    window_checked: bool = False,
    window_start: str | None = None,
    window_end: str | None = None,
    call_time: str | None = None,
    consent_checked: bool = False,
    consent_status: str | None = None,
    client_id: str | None = None,
    campaign_id: str | None = None,
    call_id: str | None = None,
    request_ip: str | None = None,
    user_agent: str | None = None,
    request_path: str | None = None,
    notes: str | None = None,
) -> bool:
    """
    Log a compliance decision to the database.

    Args:
        db: Async database session (if None, logging is skipped)
        phone: Phone number checked
        call_type: "promotional" or "transactional"
        decision_allowed: True if call was allowed
        decision_reason: Primary reason for decision ("dnd", "window", "consent", etc.)
        dnd_checked: Whether DND check was performed
        dnd_result: DND check result
        window_checked: Whether calling window was checked
        window_start: Window start time ("HH:MM")
        window_end: Window end time ("HH:MM")
        call_time: Actual call time ("HH:MM")
        consent_checked: Whether consent was verified
        consent_status: Consent status ("opted_in", "opted_out", etc.)
        client_id: Associated client ID
        campaign_id: Associated campaign ID
        call_id: Associated call log ID
        request_ip: Request IP address
        user_agent: User-Agent header (if web request)
        request_path: API endpoint path
        notes: Additional notes for auditor

    Returns:
        True if logged successfully, False if logging failed
    """
    if db is None:
        # No database session — skip logging (graceful degradation)
        return False

    try:
        # Map decision to ComplianceDecisionEnum
        if decision_allowed:
            decision_enum = ComplianceDecisionEnum.ALLOWED
        elif "dnd" in decision_reason.lower():
            decision_enum = ComplianceDecisionEnum.BLOCKED_DND
        elif "window" in decision_reason.lower() or "hour" in decision_reason.lower():
            decision_enum = ComplianceDecisionEnum.BLOCKED_WINDOW
        elif "consent" in decision_reason.lower() or "opted_out" in decision_reason.lower():
            decision_enum = ComplianceDecisionEnum.BLOCKED_CONSENT
        else:
            decision_enum = ComplianceDecisionEnum.BLOCKED_OTHER

        # Create audit log entry
        audit_log = ComplianceAuditLog(
            phone_number=phone,
            call_type=call_type,
            decision=decision_enum,
            decision_reason=decision_reason,
            dnd_checked=dnd_checked,
            dnd_result=dnd_result,
            window_checked=window_checked,
            window_start_hour=window_start,
            window_end_hour=window_end,
            call_time_hour=call_time,
            consent_checked=consent_checked,
            consent_status=consent_status,
            client_id=client_id,
            campaign_id=campaign_id,
            call_id=call_id,
            request_ip=request_ip,
            user_agent=user_agent,
            request_path=request_path,
            notes=notes,
            created_by="compliance_gate",
            created_at=datetime.utcnow(),
        )

        # Add and commit
        db.add(audit_log)
        await db.flush()  # Flush to get the ID if needed, but don't commit yet
        # (commit happens at the request level)

        logger.debug(f"✅ Compliance decision logged: {phone[:4]}*** -> {decision_enum.value}")
        return True

    except Exception as e:
        # Logging failure should NOT block the gate
        logger.warning(f"Failed to log compliance decision: {e}")
        return False
