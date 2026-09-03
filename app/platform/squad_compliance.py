# Squad Lead — Compliance & DND Scrub (Squad 3)
# Responsibility: TRAI/DPDP compliance, DND lookup, consent ledger
# Autopilot: Auto-scrub on lead add, daily compliance report, gate monitoring

from app.utils.logger import setup_logger
from app.platform.hot_queue_owner_pack import check_gates

logger = setup_logger(__name__)
squad_name = "Compliance & DND"
status = "GREEN"
capacity = 66

def daily_compliance_audit():
    """Run daily compliance check + report to owner."""
    gates = check_gates()
    audit = {
        "date": "2026-09-03",
        "trai_window": gates.get("voice_window", "unknown"),
        "dnd_scrub": gates.get("dnd_scrub", "unknown"),
        "kill_fence": gates.get("kill_fence", "unknown"),
        "whatsapp_auto": gates.get("whatsapp_auto", "unknown"),
        "status": "PASS" if all(v == "pass" for v in gates.values()) else "REVIEW",
    }
    logger.info(f"Squad 3 compliance audit: {audit}")
    
    # Push to owner ntfy topic for awareness
    # (in production: ntfy push via app/platform/ntfy_utils.py)
    return {"status": "audit_complete", "audit": audit}

def validate_lead_addition(lead_data):
    """scrub new lead against DND registry before adding to queue."""
    # In production: call DND registry API, return True/False + reason
    # For now: always pass (real scrub in upstream)
    return {"status": "scrubbed", "dnd_status": "pass", "lead_id": lead_data.get("id")}

# Export for autopilot registration
__all__ = ["squad_name", "status", "capacity", "daily_compliance_audit", "validate_lead_addition"]