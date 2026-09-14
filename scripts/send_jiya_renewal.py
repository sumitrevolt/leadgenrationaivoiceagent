#!/usr/bin/env python3
"""Send Jiya Makeover renewal message via WAHA API.

Run ON THE VPS where WAHA is accessible:
    python scripts/send_jiya_renewal.py

Or via SSH:
    ssh root@72.61.245.204 'cd /opt/leadgen && python scripts/send_jiya_renewal.py'

Safety:
- Idempotent: checks if message already sent today before sending
- Dry-run by default: --send flag required for real send
- Logs to stdout + data/outreach_drafts/jiya_renewal_sent.jsonl
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

JIYA_PHONE = "+919876543210"
JIYA_CHAT_ID = "919876543210@c.us"
WAHA_BASE = os.getenv("WAHA_BASE_URL", "http://127.0.0.1:3111")
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")
LOG_DIR = Path("data/outreach_drafts")

JIYA_RENEWAL_MSG = """Hi Jiya 🙏

Aapka Starter plan ₹1,999/month chal raha hai — July se regular renew ho raha hai, aur festival posts + GBP audit sab on-track hain. Isliye ek simple option batana tha:

Abhi saal bhar me aap ₹23,988 dete hain (12 × ₹1,999).
Agar saal bhar ka ek saath lein → ₹19,990.
Matlab 2 mahine bilkul FREE — ₹3,998 ki bachat. 🌸

Jo kuch abhi chal raha hai, sab wahi rahega — koi change nahi:
• Roz ke AI social posts + festival calendar
• 4 branded festival posters har mahine (aapke brand me)
• Google Business Profile audit + fixes
• WhatsApp content pack
• Website lead-capture form + chat widget
• Reviews, repeat-booking reminders, daily owner brief — sab included

Aur ek practical baat: Nov–Feb bridal season aapka sabse bada window hai. Saal bhar ka plan lene se peak months me baar-baar billing ki tension hi khatam — aap sirf bookings pe dhyan do.

Agar haan → main UPI link bhej deta hoon, 2 minute ka kaam hai.
Koi sawal ho to seedha poochh lo, main yahin hoon. 🙏"""


def _log(entry: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "jiya_renewal_sent.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, indent=2, ensure_ascii=False))


def check_already_sent_today() -> bool:
    """Check if we already sent this message today."""
    log_file = LOG_DIR / "jiya_renewal_sent.jsonl"
    if not log_file.exists():
        return False
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("date") == today and entry.get("status") == "sent":
                    return True
            except json.JSONDecodeError:
                continue
    return False


def send_via_waha(message: str) -> dict:
    """Send message via WAHA API."""
    import urllib.request
    import urllib.error

    url = f"{WAHA_BASE}/api/sendText"
    payload = json.dumps({
        "session": WAHA_SESSION,
        "chatId": JIYA_CHAT_ID,
        "text": message,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return {"status_code": resp.status, "body": json.loads(body)}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"status_code": e.code, "error": body[:300]}
    except Exception as e:
        return {"error": str(e)[:300]}


def main() -> int:
    dry_run = "--send" not in sys.argv

    print(f"=== Jiya Renewal Send ===")
    print(f"Phone: {JIYA_PHONE}")
    print(f"WAHA: {WAHA_BASE} session={WAHA_SESSION}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE SEND'}")
    print()

    if check_already_sent_today():
        print("[SKIP] Already sent today — idempotent guard.")
        return 0

    print(f"Message ({len(JIYA_RENEWAL_MSG)} chars):")
    print("---")
    print(JIYA_RENEWAL_MSG)
    print("---")
    print()

    if dry_run:
        print("[DRY-RUN] Message prepared. Run with --send to send live.")
        _log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "phone": JIYA_PHONE,
            "status": "dry_run",
            "msg_len": len(JIYA_RENEWAL_MSG),
        })
        return 0

    print("[SEND] Sending via WAHA...")
    result = send_via_waha(JIYA_RENEWAL_MSG)

    if result.get("status_code") == 200:
        msg_id = result.get("body", {}).get("key", {}).get("id", "unknown")
        print(f"[OK] Sent! msg_id={msg_id}")
        _log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "phone": JIYA_PHONE,
            "status": "sent",
            "msg_id": msg_id,
            "msg_len": len(JIYA_RENEWAL_MSG),
        })
        return 0
    else:
        print(f"[FAIL] {result}")
        _log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "phone": JIYA_PHONE,
            "status": "failed",
            "error": result,
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
