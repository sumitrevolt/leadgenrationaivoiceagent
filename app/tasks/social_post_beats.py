"""Beat entry: staff-daily-social-post — runs 3x daily within 9am–7pm TRAI window.

Added to app/worker.py beat schedule:
- 9:30 IST — Morning batch (own brand + active clients)
- 13:00 IST — Midday batch (own brand + active clients)
- 16:00 IST — Evening batch (own brand + active clients)

Each run generates 1 video per target (own brand + clients) and posts via Postiz.
"""

# Beat configuration for app/worker.py
BEAT_ENTRIES = {
    # Morning: 9:30 IST (after hot queue pack at 9:00)
    "staff-daily-social-post-morning": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": 34200,  # 9:30 = 9.5 * 3600 = 34200 seconds from midnight
        "args": (),
        "options": {"expires": 10800},  # 3h expiry
    },

    # Midday: 13:00 IST
    "staff-daily-social-post-midday": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": 46800,  # 13:00 = 13 * 3600 = 46800 seconds
        "args": (),
        "options": {"expires": 10800},
    },

    # Evening: 16:00 IST (before 7pm TRAI cutoff)
    "staff-daily-social-post-evening": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": 57600,  # 16:00 = 16 * 3600 = 57600 seconds
        "args": (),
        "options": {"expires": 10800},
    },
}

# Alternative: Use Celery crontab for exact times (cleaner)
from celery.schedules import crontab

CRONTAB_BEAT_ENTRIES = {
    "staff-daily-social-post-morning": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": crontab(hour=9, minute=30),
        "options": {"expires": 10800},
    },
    "staff-daily-social-post-midday": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": crontab(hour=13, minute=0),
        "options": {"expires": 10800},
    },
    "staff-daily-social-post-evening": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": crontab(hour=16, minute=0),
        "options": {"expires": 10800},
    },
}
