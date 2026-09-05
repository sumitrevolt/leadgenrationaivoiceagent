with open(r'C:\Users\Ratanshila\.openclaw\workspace\app\tasks\staff_jobs.py', 'rb') as f:
    content = f.read()

idx = content.find(b'STAFF_JOBS = (')
if idx != -1:
    end_idx = content.find(b')', idx)
    if end_idx != -1:
        if b'whatsapp_automation' not in content[idx:end_idx]:
            new_content = content[:end_idx] + b'    "whatsapp_automation",  # hourly WhatsApp automation (gated WHATSAPP_AUTO_SEND=1)\n' + content[end_idx:]
            with open(r'C:\Users\Ratanshila\.openclaw\workspace\app\tasks\staff_jobs.py', 'wb') as f:
                f.write(new_content)
            print('Added whatsapp_automation to STAFF_JOBS')
        else:
            print('Already in STAFF_JOBS')
    else:
        print('Could not find closing )')
else:
    print('STAFF_JOBS not found')