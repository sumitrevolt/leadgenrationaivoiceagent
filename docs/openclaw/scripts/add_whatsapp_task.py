with open(r'C:\Users\Ratanshila\.openclaw\workspace\app\tasks\staff_jobs.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Add the whatsapp_automation task function after boss_autonomy_sweep
# Find the last occurrence of the boss_autonomy_sweep function
if 'def boss_autonomy_sweep(self):' in content:
    # Find after the function
    insert_after = content.find('raise self.retry(exc=e)', content.find('def boss_autonomy_sweep(self):'))
    if insert_after != -1:
        # Add 2 newlines + new task
        new_task = '''\n\n@shared_task(\n    bind=True,\n    base=OwnerSchedulerGuardedTask,\n    name=\"app.tasks.staff_jobs.whatsapp_automation\",\n    max_retries=1,\n    default_retry_delay=300,\n    acks_late=True,\n)\n@idempotent_task(\"whatsapp_automation\", ttl=3600)\ndef whatsapp_automation(self):\n    \"\"\"WhatsApp full automation — hourly within 9am-7pm TRAI window.\n\n    GATED: WHATSAPP_AUTO_SEND=1 + WHATSAPP_AUTO_SEND_HARD_OFF=0\n    ⚠️ HIGH RISK: cold/bulk auto-send = number ban in 72 hours\n    Called by beat entry: staff-whatsapp-automation-hourly\n    \"\"\"\n    try:\n        from app.tasks.whatsapp_automation import run_whatsapp_automation\n\n        result = run_whatsapp_automation()\n        return {\"ok\": True, \"job\": \"whatsapp_automation\", \"result\": result}\n    except Exception as e:\n        logger.warning(f\"[whatsapp_automation] failed: {type(e).__name__}: {e}\")\n        raise self.retry(exc=e)'''

    insert_pos = content.find('raise self.retry(exc=e)', content.find('def boss_autonomy_sweep(self):'))
    if insert_pos != -1:
        # Find end of that line
        end_of_line = content.find('\\n', insert_after)
        if end_of_line != -1:
            new_content = content[:end_of_line+1] + new_task + content[end_of_line+1:]
            with open(r'C:\Users\Ratanshila\.openclaw\workspace\app\tasks\staff_jobs.py', 'w', encoding='utf-8', errors='replace') as f:
                f.write(new_content)
            print('Added whatsapp_automation task function')
        else:
            print('Could not find end of line')
    else:
        print('Could not find insertion point')
else:
    print('boss_autonomy_sweep not found')