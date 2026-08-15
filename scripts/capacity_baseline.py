#!/usr/bin/env python3
"""Read-only VPS capacity snapshot. No secrets, no recreate, no .env dump.

Usage:
    .venv\\Scripts\\python.exe scripts\\capacity_baseline.py
    .venv\\Scripts\\python.exe scripts\\capacity_baseline.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "evidence" / "capacity_baseline.json"
SSH = r"C:\PROGRA~1\Git\usr\bin\ssh.exe"
SSH_KEY = str(Path.home() / ".ssh" / "id_rsa")
VPS = "root@72.61.245.204"

# Boolean / numeric allowlist only. Never print DATABASE_URL or credential env.
_FLAG_KEYS = (
    "DSH_RUNTIME_ENABLED",
    "DSH_SHADOW_ENABLED",
    "COORDINATION_HUB_ENABLED",
    "GSC_ENABLED",
    "HARNESS_SESSION_EVENTS",
    "SALES_AUTOPILOT_WHATSAPP_ENABLED",
    "CELERY_ONBOARD_QUEUE",
    "WEB_CONCURRENCY",
    "VOICE_LAUNCH_KILL",
    "AUTO_ONBOARD",
    "SIGNUP_AUTO_ONBOARD",
    "REPLY_AGENT",
    "JOURNEY_ENGINE",
    "CADENCE_ENGINE",
    "SALES_ENGINE",
    "OPS_WATCHDOG",
    "AUTO_EMAIL_OUTREACH",
    "HOT_QUEUE_BRIEF_DAILY",
    "UPI_AUTO_ACTIVATE",
    "DUNNING_ENGINE",
)

REMOTE = r"""
set +e
echo '---STATS---'
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}} {{.MemPerc}}' | awk '/^leadgen_/'
echo '---QUEUES---'
docker exec leadgen_redis redis-cli llen celery
docker exec leadgen_redis redis-cli llen heavy
docker exec leadgen_redis redis-cli llen video
docker exec leadgen_redis redis-cli llen dsh
docker exec leadgen_redis redis-cli llen dlq:failed_tasks
docker exec leadgen_redis redis-cli llen dlq:dead
echo '---REDISMEM---'
docker exec leadgen_redis redis-cli info memory | awk -F: '/^(used_memory_human|maxmemory_human|evicted_keys)/{gsub(/\r/,""); print}'
echo '---FLAGS---'
docker exec leadgen_app python -c 'import os; ks="DSH_RUNTIME_ENABLED DSH_SHADOW_ENABLED COORDINATION_HUB_ENABLED GSC_ENABLED HARNESS_SESSION_EVENTS SALES_AUTOPILOT_WHATSAPP_ENABLED CELERY_ONBOARD_QUEUE WEB_CONCURRENCY VOICE_LAUNCH_KILL AUTO_ONBOARD SIGNUP_AUTO_ONBOARD REPLY_AGENT JOURNEY_ENGINE CADENCE_ENGINE SALES_ENGINE OPS_WATCHDOG AUTO_EMAIL_OUTREACH HOT_QUEUE_BRIEF_DAILY UPI_AUTO_ACTIVATE DUNNING_ENGINE".split();
[print("%s=%s"%(k,"UNSET" if os.environ.get(k) is None else ((os.environ.get(k) or "").strip()[:8] if k=="WEB_CONCURRENCY" else ("1" if (os.environ.get(k) or "").strip().lower() in ("1","true","yes","on") else "0")))) for k in ks]'
echo '---PG---'
docker exec leadgen_db psql -U postgres -d leadgen -tAc "select count(*) from pg_stat_activity" 2>/dev/null || echo skipped
echo '---DBHOST---'
docker exec leadgen_app python -c 'import os; u=os.environ.get("DATABASE_URL") or ""; host=u.split("@")[-1].split("/")[0].lower() if "@" in u else ""; print("via_pgbouncer", "pgbouncer" in host and ":6432" in host); print("direct_db_5432", "db:5432" in host or "@db:" in host)'
echo '---CODE---'
docker exec leadgen_app python -c 'from app.platform import office_briefing, upi_payments; print("notify_owner_once", hasattr(office_briefing, "_notify_owner_once")); print("list_actionable", hasattr(upi_payments, "list_actionable"))'
echo '---HOST---'
free -m | awk "NR==2{print \"mem_used_mb=\" \$3 \" mem_total_mb=\" \$2}"
uptime
echo '---HEALTH---'
curl -fsS http://127.0.0.1:8000/health
echo
echo '---ACTIVATION---'
curl -fsS http://127.0.0.1:8000/api/activation/summary
echo
echo '---BLOCKERS---'
docker exec leadgen_app python -c 'from app.api.activation import _PROBES; items=[p() for p in _PROBES]; print(",".join(it["key"] for it in items if it.get("status")=="BLOCKER") or "none")'
"""


def fetch() -> str:
    r = subprocess.run(
        [SSH, "-i", SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", VPS, REMOTE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    if r.returncode != 0:
        raise SystemExit(f"ssh failed rc={r.returncode}: {(r.stderr or '')[:300]}")
    return r.stdout or ""


def parse(raw: str) -> dict:
    out: dict = {
        "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "raw_ok": True,
    }
    section = None
    stats: list[str] = []
    queues: list[str] = []
    flags: list[str] = []
    redis_mem: list[str] = []
    host: list[str] = []
    pg: list[str] = []
    dbhost: list[str] = []
    code: list[str] = []
    for line in raw.splitlines():
        if line.startswith("---") and line.endswith("---"):
            section = line.strip("-").lower()
            continue
        if not line.strip():
            continue
        if section == "stats":
            stats.append(line.strip())
        elif section == "queues":
            queues.append(line.strip())
        elif section == "flags":
            flags.append(line.strip())
        elif section == "redismem":
            redis_mem.append(line.strip())
        elif section == "pg":
            pg.append(line.strip())
        elif section == "dbhost":
            dbhost.append(line.strip())
        elif section == "code":
            code.append(line.strip())
        elif section == "host":
            host.append(line.strip())
        elif section == "health":
            try:
                out["health"] = json.loads(line)
            except json.JSONDecodeError:
                out["health_line"] = line[:200]
        elif section == "activation":
            try:
                out["activation"] = json.loads(line)
            except json.JSONDecodeError:
                out["activation_line"] = line[:200]
        elif section == "blockers":
            out["blocker_keys"] = [p for p in line.split(",") if p and p != "none"]
    out["stats"] = stats
    names = ["celery", "heavy", "video", "dsh", "dlq:failed_tasks", "dlq:dead"]
    out["queues"] = {}
    for i, name in enumerate(names):
        if i < len(queues):
            try:
                out["queues"][name] = int(queues[i])
            except ValueError:
                out["queues"][name] = queues[i]
    parsed_flags: dict[str, str] = {}
    for row in flags:
        if "=" in row:
            k, _, v = row.partition("=")
            if k in _FLAG_KEYS:
                parsed_flags[k] = v.strip()[:16]
    out["flags"] = parsed_flags
    out["redis_mem"] = redis_mem
    out["pg"] = pg
    out["dbhost"] = dbhost
    out["code_locks"] = code
    out["host"] = host
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    raw = fetch()
    row = parse(raw)
    print(json.dumps(row, indent=2, sort_keys=True)[:4000])
    if args.dry_run:
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
