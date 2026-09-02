#!/usr/bin/env python3
"""Lightweight SMTP alert for the VPS health watchdog.

Reads SMTP creds straight from /opt/leadgen/.env (no app import, no extra deps) and
emails NOTIFY_EMAIL (falls back to EMAIL_FROM / SMTP_USER). Reuses the existing
Hostinger mailbox already configured for the app. Never raises — a mail hiccup must
not break the monitor.

Usage:  python3 alert_email.py "the alert message"
"""

import os
import smtplib
import ssl
import sys
from email.mime.text import MIMEText


def load_env(path: str = "/opt/leadgen/.env") -> dict:
    env: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return env


def main() -> None:
    body = " ".join(sys.argv[1:]).strip() or "LeadGen VPS alert"
    e = load_env(os.environ.get("ENV_FILE", "/opt/leadgen/.env"))

    host = e.get("SMTP_HOST", "smtp.hostinger.com")
    try:
        port = int(e.get("SMTP_PORT", "465") or 465)
    except Exception:
        port = 465
    user = e.get("SMTP_USER") or e.get("EMAIL_FROM") or "admin@leadsgenai.in"
    pw = e.get("SMTP_PASSWORD", "")
    to = e.get("NOTIFY_EMAIL") or e.get("EMAIL_FROM") or user

    if not (user and pw and to):
        print("alert email skipped: SMTP creds missing in .env")
        return

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = "[LeadGen] VPS health alert"
    msg["From"] = user
    msg["To"] = to

    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                s.login(user, pw)
                s.sendmail(user, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(user, pw)
                s.sendmail(user, [to], msg.as_string())
        print(f"alert email sent to {to}")
    except Exception as ex:  # pragma: no cover - best effort
        print(f"alert email failed: {ex}")


if __name__ == "__main__":
    main()
