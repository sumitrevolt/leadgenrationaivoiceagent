with open(r'C:\Users\Ratanshila\.openclaw\workspace\app\tasks\staff_jobs.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Add the whatsapp_automation task function at the end of the file
new_task = '''

@shared_task(
    bind=True,
    base=OwnerSchedulerGuardedTask,
    name="app.tasks.staff_jobs.whatsapp_automation",
    max_retries=1,
    default_retry_delay=300,
    acks_late=True,
)
@idempotent_task("whatsapp_automation", ttl=3600)
def whatsapp_automation(self):
    """WhatsApp full automation — hourly within 9am-7pm TRAI window.

    GATED: WHATSAPP_AUTO_SEND=1 + WHATSAPP_AUTO_SEND_HARD_OFF=0
    ⚠️ HIGH RISK: cold/bulk auto-send = number ban in 72 hours
    Called by beat entry: staff-whatsapp-automation-hourly
    """
    try:
        from app.tasks.whatsapp_automation import run_whatsapp_automation

        result = run_whatsapp_automation()
        return {"ok": True, "job": "whatsapp_automation", "result": result}
    except Exception as e:
        logger.warning(f"[whatsapp_automation] failed: {type(e).__name__}: {e}")
        raise self.retry(exc=e)
'''

if 'def whatsapp_automation(self):' not in content:
    content = content.rstrip() + new_task + '\n'
    with open(r'C:\Users\Ratanshila\.openclaw\workspace\app\tasks\staff_jobs.py', 'w', encoding='utf-8', errors='replace') as f:
        f.write(content)
    print('Added whatsapp_automation task function at end of file')
else:
    print('Already exists')