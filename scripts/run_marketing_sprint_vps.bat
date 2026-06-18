@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0marketing_sprint_vps.log

echo === Marketing Sprint VPS === > "%LOG%"
echo [%date% %time%] >> "%LOG%"

echo --- SCP script --- >> "%LOG%"
"%SCP%" -i "%KEY%" -o StrictHostKeyChecking=no "%~dp0marketing_sprint_today.py" %HOST%:/tmp/marketing_sprint_today.py >> "%LOG%" 2>&1
if errorlevel 1 goto :fail

echo --- SCP inquiry test --- >> "%LOG%"
"%SCP%" -i "%KEY%" -o StrictHostKeyChecking=no "%~dp0inquiry_notify_test.py" %HOST%:/tmp/inquiry_notify_test.py >> "%LOG%" 2>&1

echo --- docker cp + run --- >> "%LOG%"
"%SSH%" -i "%KEY%" -o StrictHostKeyChecking=no %HOST% "docker cp /tmp/marketing_sprint_today.py leadgen_app:/app/scripts/marketing_sprint_today.py && docker cp /tmp/inquiry_notify_test.py leadgen_app:/app/scripts/inquiry_notify_test.py && docker exec leadgen_app python /app/scripts/inquiry_notify_test.py && docker exec leadgen_app python /app/scripts/marketing_sprint_today.py" >> "%LOG%" 2>&1
if errorlevel 1 goto :fail

echo --- tail inquiries --- >> "%LOG%"
"%SSH%" -i "%KEY%" -o StrictHostKeyChecking=no %HOST% "docker exec leadgen_app tail -n 1 /app/data/inquiries.jsonl 2>/dev/null | head -c 300" >> "%LOG%" 2>&1

echo DONE >> "%LOG%"
exit /b 0

:fail
echo FAIL >> "%LOG%"
exit /b 1
