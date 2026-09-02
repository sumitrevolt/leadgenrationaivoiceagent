"""Idempotently enable the ready+safe feature flags in /opt/leadgen/.env (+ backup).

Run on VPS: cd /opt/leadgen && .venv/bin/python scripts/enable_flags.py
Then restart: systemctl restart leadgen
"""

import shutil
import sys

ENV = "/opt/leadgen/.env"
# Only flags whose deps + keys are READY (per setup audit) and that take effect safely.
FLAGS = {
    "REPLY_AGENT": "1",  # AI inbox reply triage (SMTP/IMAP + free_ai ready)
    "OPS_WATCHDOG": "1",  # ops monitoring + email alerts (NOTIFY_EMAIL set)
    "AUTO_ONBOARD": "1",  # auto client onboarding (website->KB)
    "USE_STRUCTURED_CONTENT": "1",  # typed marketing content (instructor installed)
}

try:
    shutil.copy(ENV, ENV + ".bak")
    lines = open(ENV, encoding="utf-8").read().splitlines()
    seen = set()
    out = []
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in FLAGS:
                out.append(f"{k}={FLAGS[k]}")
                seen.add(k)
                continue
        out.append(ln)
    for k, v in FLAGS.items():
        if k not in seen:
            out.append(f"{k}={v}")
    open(ENV, "w", encoding="utf-8").write("\n".join(out).rstrip("\n") + "\n")
    print("ENABLED:", ", ".join(f"{k}={v}" for k, v in FLAGS.items()))
    print("backup saved:", ENV + ".bak")
except Exception as e:
    print("enable_flags error:", e)
    sys.exit(1)
