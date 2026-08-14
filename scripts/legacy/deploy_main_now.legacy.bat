@echo off
setlocal
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204

echo === Push main ===
call "%GIT%" push origin main
if errorlevel 1 exit /b 1

echo === VPS deploy ===
"%SSH%" -i "%KEY%" -o StrictHostKeyChecking=no -o BatchMode=yes %HOST% "bash -lc 'set -e; cd /opt/leadgen; git fetch --all -q; git reset --hard origin/main -q; bash scripts/vps_migrate_qdrant.sh; python3 scripts/vps_enable_readiness_flags.py || true; docker compose -f docker-compose.vps.yml build app; docker compose -f docker-compose.vps.yml up -d --no-deps app; docker compose -f docker-compose.vps.yml --profile celery up -d worker worker-heavy scheduler; sleep 18; curl -sf http://127.0.0.1:8000/health; echo; python3 scripts/vps_post_deploy_verify.py'"
exit /b %ERRORLEVEL%
