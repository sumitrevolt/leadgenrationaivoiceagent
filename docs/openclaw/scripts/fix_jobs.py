with open(r'C:\Users\Ratanshila\.openclaw\workspace\app\tasks\staff_jobs.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Add whatsapp_automation before closing parenthesis
if '\"trial_nudge\"' in content:
    content = content.replace(
        '\"trial_nudge\",  # daily 09:50 IST trial expiry/expired Starter UPI nudge EMAIL (gated TRIAL_NUDGE_ENABLED; INERT off',
        '\"trial_nudge\",  # daily 09:50 IST trial expiry/expired Starter UPI nudge EMAIL (gated TRIAL_NUDGE_ENABLED; INERT off\n    \"whatsapp_automation\",  # hourly WhatsApp automation (gated WHATSAPP_AUTO_SEND=1)'
    )
    with open(r'C:\Users\Ratanshila\.openclaw\workspace\app\tasks\staff_jobs.py', 'w', encoding='utf-8', errors='replace') as f:
        f.write(content)
    print('Done')
else:
    print('trial_nudge not found')