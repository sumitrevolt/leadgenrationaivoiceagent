$sshExe = 'C:\PROGRA~1\Git\usr\bin\ssh.exe'
$sshKey = 'C:\Users\Ratanshila\.ssh\id_rsa'
$vpsHost = 'root@72.61.245.204'

$scriptContent = @'
set -euo pipefail
echo '=== VPS Full Runtime Probe ==='
echo '--- System Resources ---'
df -h / | tail -1
free -h | head -2
uptime
echo '--- Docker Containers (app-image services) ---'
docker ps --filter 'label=com.docker.compose.project=leadgen' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E 'leadgen_app|leadgen_worker|leadgen_scheduler|leadgen_dsh'
echo '--- Docker Images (app) ---'
docker images --filter 'reference=ghcr.io/sumitrevolt/leadgenrationaivoiceagent*' --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}' | head -10
echo '--- Disk Usage ---'
du -sh /var/lib/docker 2>/dev/null || true
docker system df 2>/dev/null || true
echo '--- Redis Health ---'
docker exec leadgen_redis redis-cli ping 2>/dev/null || echo 'Redis not reachable'
echo '--- Celery Queues ---'
docker exec leadgen_redis redis-cli llen celery 2>/dev/null || echo 'celery queue check failed'
docker exec leadgen_redis redis-cli llen dlq:failed_tasks 2>/dev/null || echo 'dlq check failed'
docker exec leadgen_redis redis-cli llen dlq:dead 2>/dev/null || echo 'dlq:dead check failed'
echo '--- /health endpoints ---'
curl -s http://127.0.0.1:8000/health | head -c 500
echo
curl -s http://127.0.0.1:8000/health/ready | head -c 200
echo
echo '--- Systemd Services ---'
systemctl status leadgen --no-pager | head -10
systemctl status leadgen-call-loop --no-pager | head -10 2>/dev/null || true
echo '--- Deploy Log ---'
tail -20 /tmp/dep.log 2>/dev/null || echo 'No deploy log found'
'@

$scriptContent | Out-File -FilePath 'C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\scripts\vps_probe_remote.sh' -Encoding ASCII

Write-Host "Script written to local path"
Write-Host "Uploading to VPS and executing..."

# Use scp to upload the script
$scpCmd = "& '$sshExe' -i '$sshKey' -o StrictHostKeyChecking=no -o ConnectTimeout=15 '$vpsHost' 'bash /tmp/vps_probe_remote.sh'"
Invoke-Expression $scpCmd
