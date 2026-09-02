"""SMTP host/port diagnostic — creds .env (settings) se padhta hai, koi secret yahan nahi."""

import smtplib

from app.config import settings

u = (settings.smtp_user or "").strip()
p = (settings.smtp_password or "").strip()
print("USER:", u, "| pwd_len:", len(p))

for host in ["smtp.hostinger.com", "smtp.titan.email"]:
    for port in (465, 587):
        try:
            if port == 465:
                s = smtplib.SMTP_SSL(host, port, timeout=12)
            else:
                s = smtplib.SMTP(host, port, timeout=12)
                s.ehlo()
                s.starttls()
                s.ehlo()
            s.login(u, p)
            s.quit()
            print(f"OK  {host}:{port}")
        except Exception as e:
            print(f"FAIL {host}:{port} -> {str(e)[:80]}")
