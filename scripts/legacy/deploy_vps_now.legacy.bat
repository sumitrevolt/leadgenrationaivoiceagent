@echo off

setlocal

set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe

set KEY=C:\Users\Ratanshila\.ssh\id_rsa

set HOST=root@72.61.245.204

set LOG=%~dp0deploy_vps.log



echo === VPS Deploy 5d3d083 test-call fix === > "%LOG%"

echo [%date% %time%] >> "%LOG%"



"%SSH%" -i "%KEY%" -o StrictHostKeyChecking=no %HOST% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app" >> "%LOG%" 2>&1

if errorlevel 1 goto :fail



echo --- health check --- >> "%LOG%"

ping -n 17 127.0.0.1 >nul

"%SSH%" -i "%KEY%" -o StrictHostKeyChecking=no %HOST% "curl -fsS http://127.0.0.1:8000/health && echo OK && curl -fsS -o /dev/null -w 'test-call %%{http_code}\n' http://127.0.0.1:8000/app/test-call" >> "%LOG%" 2>&1

if errorlevel 1 goto :fail



echo DONE >> "%LOG%"

exit /b 0



:fail

echo FAIL >> "%LOG%"

exit /b 1
