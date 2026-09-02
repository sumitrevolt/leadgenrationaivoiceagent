@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0vps_vobiz_go_live.log

echo [%date% %time%] Vobiz go-live > "%LOG%"

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "cd /opt/leadgen && python3 scripts/env_set.py TELEPHONY_PROVIDER=vobiz VOBIZ_CALLER_ID=+911171366938 DLT_APPROVED=1 TELEPHONY_READY_ALERTS=1" >> "%LOG%" 2>&1
if errorlevel 1 goto fail

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "cd /opt/leadgen && docker compose -f docker-compose.vps.yml up -d --no-deps app worker && sleep 18" >> "%LOG%" 2>&1
if errorlevel 1 goto fail

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 scripts/vobiz_go_live.py" >> "%LOG%" 2>&1
if errorlevel 1 goto fail

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "curl -s http://127.0.0.1:8000/api/webhooks/health" >> "%LOG%" 2>&1

echo DONE >> "%LOG%"
exit /b 0

:fail
echo FAIL >> "%LOG%"
exit /b 1
