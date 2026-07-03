# Backup Scheduler Ticker (optional, dormant)

**Primary scheduler = Celery beat** (`docker-compose.vps.yml --profile celery`, `leadgen_scheduler` container) — yeh usse REPLACE nahi karta.

Yeh folder ek **dead-man BACKUP ticker** hai (dependency-free `leadgen_scheduler.py`): har 15 min `POST /api/platform/team/scheduler/run-due` hit karta hai. Woh endpoint sirf **overdue/never-ran** agent-jobs ko re-dispatch karta hai (bounded `max_jobs`, `RUN_DUE_EXCLUDE` = platform_dial/email_outreach/email_followup kabhi auto-recover nahi — outbound apni window ke bahar dobara nahi jaata). Sab kuch normal chal raha ho to har tick **no-op** hai.

## Activate (VPS, optional)

```bash
sudo mkdir -p /opt/leadgen-scheduler /var/log/leadgen
sudo cp leadgen_scheduler.py /opt/leadgen-scheduler/
sudo cp .env.scheduler.example /opt/leadgen-scheduler/.env.scheduler   # edit: SECRET set karo
sudo cp systemd/leadgen-scheduler.timer systemd/leadgen-scheduler-run-once.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leadgen-scheduler.timer   # timer mode (recommended)
```

App-side: `/opt/leadgen/.env` me SAME `LEADGEN_SCHEDULER_SECRET` set karo + app recreate. Secret unset = endpoint 503 fail-CLOSED (ticker harmless).

Verify:

```bash
systemctl list-timers | grep leadgen
curl -s -X POST -H "Authorization: Bearer $SECRET" http://127.0.0.1:8000/api/platform/team/scheduler/run-due
```

NOTE: systemd units `User=www-data` use karte hain — VPS pe chahe to `root` kar do (units edit).
