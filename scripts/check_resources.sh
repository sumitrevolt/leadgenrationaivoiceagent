#!/usr/bin/env bash
# check_resources.sh — read-only: VPS production capacity + backup freshness
set +e
echo "===DISK==="
df -h / /var/lib/docker 2>/dev/null | grep -v tmpfs
echo "===DISK: biggest consumers under /opt + docker==="
docker system df 2>/dev/null
echo "===MEMORY==="
free -m | head -2
echo "===LOAD (4 cores)==="
uptime
echo "===TOP 5 CONTAINERS BY MEM==="
docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}' 2>/dev/null | sort -t'|' -k2 -hr | head -6
echo "===DANGLING IMAGES (old builds pile up: I built 5 today)==="
docker images -f dangling=true -q 2>/dev/null | wc -l
docker images ghcr.io/sumitrevolt/leadgenrationaivoiceagent --format '{{.Tag}}|{{.Size}}|{{.CreatedSince}}' 2>/dev/null | head -10
echo "===BACKUP FRESHNESS==="
ls -lat /opt/leadgen/backups 2>/dev/null | head -4
echo "--- offsite (rclone) last run ---"
grep -h "" /var/log/leadgen_backup*.log 2>/dev/null | tail -3 || echo "(no local backup log at that path)"
echo "===POSTGRES SIZE==="
docker exec leadgen_db psql -U postgres -d leadgen -c "SELECT pg_size_pretty(pg_database_size('leadgen'));" 2>/dev/null | head -4
echo "===RES_DONE==="
