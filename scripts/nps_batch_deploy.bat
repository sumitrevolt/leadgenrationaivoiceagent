@echo off
REM Prod-batch deploy: NPS + recon + IndexNow. Log -> nps_batch_deploy.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set LOG=nps_batch_deploy.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === VPS pull === > %LOG%
call %SSH% "cd /opt/leadgen && git stash -u -q 2>/dev/null; git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo EXIT_PULL=%errorlevel% >> %LOG%
echo === build app image === >> %LOG%
call %SSH% "cd /opt/leadgen && docker compose -f docker-compose.vps.yml build app 2>&1 | tail -5" >> %LOG% 2>&1
echo EXIT_BUILD=%errorlevel% >> %LOG%
echo === recreate (app/worker/scheduler jinki image badli) === >> %LOG%
call %SSH% "cd /opt/leadgen && docker compose -f docker-compose.vps.yml --profile celery up -d 2>&1 | tail -8" >> %LOG% 2>&1
echo EXIT_UP=%errorlevel% >> %LOG%
ping -n 17 127.0.0.1 >nul
call %SSH% "curl -s -o /dev/null -w 'HEALTH1=%%{http_code}' http://127.0.0.1:8000/health; echo" >> %LOG% 2>&1
ping -n 6 127.0.0.1 >nul
echo === smoke === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/health/ready | head -c 300; echo; curl -s -o /dev/null -w 'EXT=%%{http_code}' https://leadsgenai.in/health; echo; echo -n KEYFILE=; curl -s http://127.0.0.1:8000/indexnow-key.txt | head -c 36; echo; docker ps --format '{{.Names}} {{.Status}}' | grep -c Up" >> %LOG% 2>&1
echo === DONE === >> %LOG%
