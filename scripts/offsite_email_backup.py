#!/usr/bin/env python3
"""Offsite backup via EMAIL — nightly DB dump + data/ tarball ko Hostinger
mailbox (NOTIFY_EMAIL) pe attach karke bhejta hai.

KYU: saare backups abhi USI VPS ki disk pe the (VPS gaya = sab gaya). R2/B2
creds abhi nahi hain — Hostinger mail ALAG infra hai, isliye yeh free+real
offsite hai jab tak object-storage nahi aata. DB chhota hai (~75KB gz) to
email attach bilkul theek; 18MB cap ke upar DB-only ya alert bhejta hai.

HOST pe chalao (stdlib-only, no deps):  python3 scripts/offsite_email_backup.py
Cron (suggested):  0 23 * * *  → 04:30 IST daily (pg_backup 02:30 ke baad).
Never-raise: har failure log-line ke saath exit 0 (cron spam nahi).
"""

from __future__ import annotations

import glob
import io
import os
import smtplib
import ssl
import sys
import tarfile
import time
from datetime import datetime
from email.message import EmailMessage

BASE = os.environ.get("LEADGEN_BASE", "/opt/leadgen")
ENV_FILE = os.path.join(BASE, ".env")
BACKUP_GLOB = os.path.join(BASE, "backups", "*.gz")
DATA_DIR = os.path.join(BASE, "data")
# media/cache subdirs — backup me nahi chahiye (regenerable, size bloat)
EXCLUDE_DIRS = {
    "ai_images",
    "reels",
    "jingles",
    "bg_removed",
    "vectorstore",
    "conversations",
    "logos",
}
MAX_ATTACH = 18 * 1024 * 1024  # 18MB (mail server 25MB limit se neeche)


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().isoformat()}Z] {msg}", flush=True)


def load_env(path: str) -> dict:
    env: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        log(f"env read fail: {e}")
    return env


def newest_dump() -> str | None:
    files = sorted(glob.glob(BACKUP_GLOB), key=os.path.getmtime)
    return files[-1] if files else None


def tar_data() -> bytes | None:
    try:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for root, dirs, files in os.walk(DATA_DIR):
                rel = os.path.relpath(root, DATA_DIR)
                top = rel.split(os.sep)[0]
                if top in EXCLUDE_DIRS:
                    dirs[:] = []
                    continue
                for fn in files:
                    fp = os.path.join(root, fn)
                    try:
                        if os.path.getsize(fp) > 8 * 1024 * 1024:
                            continue  # koi bada stray file skip
                        tar.add(fp, arcname=os.path.join("data", rel, fn))
                    except Exception:
                        continue
        return buf.getvalue()
    except Exception as e:
        log(f"data tar fail: {e}")
        return None


def main() -> int:
    env = load_env(ENV_FILE)
    host = env.get("SMTP_HOST", "smtp.hostinger.com")
    port = int(env.get("SMTP_PORT") or 465)
    user = env.get("SMTP_USER") or env.get("EMAIL_FROM")
    pwd = env.get("SMTP_PASSWORD")
    to = env.get("NOTIFY_EMAIL") or user
    if not (user and pwd and to):
        log("SMTP creds/NOTIFY_EMAIL missing — skip (offsite mail inert)")
        return 0

    dump = newest_dump()
    dump_bytes = b""
    if dump:
        try:
            with open(dump, "rb") as f:
                dump_bytes = f.read()
        except Exception as e:
            log(f"dump read fail: {e}")
    data_bytes = tar_data() or b""

    today = datetime.utcnow().strftime("%Y-%m-%d")
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = (
        f"[leadsgenai OFFSITE BACKUP] {today} — db {len(dump_bytes) // 1024}KB + data {len(data_bytes) // 1024}KB"
    )
    parts = []
    total = 0
    if dump_bytes and total + len(dump_bytes) <= MAX_ATTACH:
        parts.append((os.path.basename(dump), dump_bytes))
        total += len(dump_bytes)
    if data_bytes and total + len(data_bytes) <= MAX_ATTACH:
        parts.append((f"data_{today}.tar.gz", data_bytes))
        total += len(data_bytes)
    body = (
        f"Nightly offsite backup (email-based, R2/B2 aane tak).\n"
        f"DB dump: {dump or 'NONE'} ({len(dump_bytes) // 1024}KB)\n"
        f"data/ tarball: {len(data_bytes) // 1024}KB (media-cache excluded)\n"
        f"Attached: {[p[0] for p in parts] or 'NONE (size cap/missing) — CHECK BACKUPS!'}\n"
        f"Restore: gunzip dump → pg_restore; tar -xzf data tarball.\n"
    )
    msg.set_content(body)
    for name, blob in parts:
        msg.add_attachment(blob, maintype="application", subtype="gzip", filename=name)

    for attempt in (1, 2):
        try:
            with smtplib.SMTP_SSL(
                host, port, context=ssl.create_default_context(), timeout=30
            ) as s:
                s.login(user, pwd)
                s.send_message(msg)
            log(f"SENT to {to} — attachments={[p[0] for p in parts]} total={total // 1024}KB")
            return 0
        except Exception as e:
            log(f"send attempt {attempt} fail: {e}")
            time.sleep(5)
    log("OFFSITE MAIL FAILED (dono attempts)")
    return 0  # cron-friendly


if __name__ == "__main__":
    sys.exit(main())
