# Squad Lead — Voice Calling Agent (Squad 1)
# Responsibility: Outbound calls within TRAI 9am–7pm window, DND scrub, DLT-gated
# Autopilot: Beat-driven, priority-queued, compliance-gated

from app.utils.logger import setup_logger
from app.platform.hot_queue_owner_pack import build_owner_pack
from app.platform.team_scheduler import STAFF_JOBS_VALID

logger = setup_logger(__name__)
squad_name = "Voice Calling"
status = "GREEN"
capacity = 66

def check_compliance():
    """Verify TRAI window + DND + kill-fence before any call execution."""
    from app.platform.hot_queue_owner_pack import check_gates
    gates = check_gates()
    open_gates = [k for k, v in gates.items() if v != "pass"]
    if open_gates:
        logger.warning(f"Squad {squad_name} blocked by open gates: {open_gates}")
        return False
    # Verify we're within 9am–7pm IST
    import datetime, pytz
    ist = pytz.timezone("Asia/Calcutta")
    now_ist = datetime.datetime.now(ist)
    hour = now_ist.hour
    if hour < 9 or hour > 19:  # 9am–7pm inclusive
        logger.info(f"Outside TRAI window (hour={hour}) — skipping calls")
        return False
    return True

def run_daily_beat():
    """Execute the daily hot-queue owner pack generation."""
    if not check_compliance():
        return {"status": "skipped", "reason": "compliance_or_window"}
    
    result = build_owner_pack(limit=42, push_ntfy=True)
    logger.info(f"Squad 1 beat completed: {result}")
    return result

def run_hourly_outreach():
    """Execute hourly outreach within daily cap (80/day = ~3/hour peak)."""
    if not check_compliance():
        return {"status": "skipped", "reason": "compliance"}
    
    # Celery beat handles hourly 9-19 distribution
    # This function is called by the beat entry
    from app.tasks.staff_jobs import process_outreach_cycle
    result = process_outreach_cycle()
    logger.info(f"Squad 1 hourly outreach: {result}")
    return result

# Export for autopilot registration
__all__ = ["squad_name", "status", "capacity", "check_compliance", "run_daily_beat", "run_hourly_outreach"]