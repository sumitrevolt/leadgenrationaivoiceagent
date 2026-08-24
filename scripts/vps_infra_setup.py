"""VPS infra setup: pg_backup cron, logrotate, PLAN_RATE_LIMIT, REQUEST_GUARD.
Run on VPS: python3 scripts/vps_infra_setup.py
"""

import os
import subprocess
import sys

LOG = []


def run(cmd, shell=True):
    r = subprocess.run(cmd, shell=shell, capture_output=True, text=True)  # nosec B602 (ops script, explicit shell)
    out = (r.stdout + r.stderr).strip()
    LOG.append(f"$ {cmd}\n{out}")
    return r.returncode, out


ok = True

# 1) logrotate
rc, _ = run("cp /opt/leadgen/scripts/logrotate_leadgen.conf /etc/logrotate.d/leadgen")
LOG.append("logrotate: " + ("OK" if rc == 0 else "FAIL"))

# 2) pg_backup cron (idempotent)
rc, cur = run("crontab -l 2>/dev/null || true")
if "pg_backup.sh" in cur:
    LOG.append("cron: pg_backup already set")
else:
    new_cron = (
        cur
        + "\n30 21 * * * /opt/leadgen/scripts/pg_backup.sh >> /var/log/leadgen_backup.log 2>&1\n"
    )
    rc2, _ = run(f'echo "{new_cron}" | crontab -')
    LOG.append("cron: pg_backup added " + ("OK" if rc2 == 0 else "FAIL"))

# 3) backup dirs
os.makedirs("/opt/leadgen/backups/metrics", exist_ok=True)
os.makedirs("/opt/leadgen/backups", exist_ok=True)
LOG.append("backup dirs: OK")

# 4) PLAN_RATE_LIMIT + REQUEST_GUARD in .env
env_file = "/opt/leadgen/.env"
try:
    with open(env_file) as f:
        content = f.read()
    changed = False
    for var in ("PLAN_RATE_LIMIT", "REQUEST_GUARD"):
        import re

        if re.search(rf"^{var}=", content, re.MULTILINE):
            content = re.sub(rf"^{var}=.*$", f"{var}=1", content, flags=re.MULTILINE)
            LOG.append(f"{var}: updated to 1")
        else:
            content += f"\n{var}=1\n"
            LOG.append(f"{var}: added")
        changed = True
    if changed:
        with open(env_file, "w") as f:
            f.write(content)
        LOG.append(".env: written OK")
except Exception as e:
    LOG.append(f".env: ERROR {e}")

# 5) Start observability stack (if not running)
rc, running = run("docker ps --format '{{.Names}}' | grep leadgen_prometheus || true")
if "leadgen_prometheus" in running:
    LOG.append("observability: already running")
else:
    rc2, out2 = run(
        "cd /opt/leadgen && docker compose -f deploy/compose/docker-compose.observability.yml up -d 2>&1 | tail -10"
    )
    LOG.append("observability start: " + ("OK" if rc2 == 0 else f"FAIL\n{out2}"))

# 6) alertmanager SMTP password
smtp_pass = os.environ.get("SMTP_PASSWORD", "")
if smtp_pass:
    try:
        with open("/opt/leadgen/monitoring/alertmanager_smtp_pass", "w") as f:
            f.write(smtp_pass)
        os.chmod("/opt/leadgen/monitoring/alertmanager_smtp_pass", 0o600)
        LOG.append("alertmanager_smtp_pass: written")
    except Exception as e:
        LOG.append(f"alertmanager_smtp_pass: {e}")
else:
    LOG.append("alertmanager_smtp_pass: SMTP_PASSWORD not set — skip")

# Print results
print("\n".join(LOG))
print("\n=== INFRA SETUP DONE ===")
