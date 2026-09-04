"""Beat entry: staff-whatsapp-automation-hourly — runs hourly within 9am-7pm TRAI window.

Added to app/worker.py beat schedule.
"""

from celery.schedules import crontab

CRONTAB_BEAT_ENTRIES = {
    # Hourly WhatsApp automation within TRAI window (9am-7pm)
    "staff-whatsapp-automation-hourly": {
        "task": "app.tasks.whatsapp_automation.run_whatsapp_automation",
        "schedule": crontab(hour="9,10,11,12,13,14,15,16,17,18,19", minute=0),
        "options": {"expires": 3600},  # 1h expiry
    },
}
