# Squad Lead — Marketing Automation (Squad 2)
# Responsibility: Email outreach, campaign management, lead nurture
# Autopilot: Hourly cron within OUTREACH_DAILY_CAP=80, TRAI-compliant windows

from app.utils.logger import setup_logger
from app.config.settings import settings
import os

logger = setup_logger(__name__)
squad_name = "Marketing Automation"
status = "GREEN"
capacity = 66

def check_compliance():
    """Verify compliance gates before any outreach execution."""
    from app.platform.hot_queue_owner_pack import check_gates
    gates = check_gates()
    open_gates = [k for k, v in gates.items() if v != "pass"]
    if open_gates:
        logger.warning(f"Squad {squad_name} blocked by open gates: {open_gates}")
        return False
    return True

def run_hourly_campaign():
    """Execute one hour of outreach within daily cap."""
    if not check_compliance():
        return {"status": "skipped", "reason": "compliance"}
    
    # Read current count from Redis or file
    daily_cap = int(os.getenv("OUTREACH_DAILY_CAP", "80"))
    # In production: check Redis INCR for today's count
    # For now: simulate execution
    logger.info(f"Squad 2 hourly campaign — daily cap: {daily_cap}")
    return {"status": "executed", "outreach_this_hour": min(5, daily_cap // 11)}

def run_daily_stats():
    """Generate outreach statistics for owner dashboard."""
    import os, json
    data_dir = settings.DATA_DIR
    stats_path = os.path.join(data_dir, "outreach_stats.json")
    
    if os.path.exists(stats_path):
        with open(stats_path) as f:
            stats = json.load(f)
    else:
        stats = {"total_outreach": 0, "replies": 0, "closes": 0, "date": None}
    
    return {"status": "retrieved", "stats": stats}

# Export for autopilot registration
__all__ = ["squad_name", "status", "capacity", "check_compliance", "run_hourly_campaign", "run_daily_stats"]