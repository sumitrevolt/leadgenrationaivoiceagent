@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0inquiry_notify_test.log

echo === inquiry notify test === > "%LOG%"
"%SCP%" -i "%KEY%" -o StrictHostKeyChecking=no "%~dp0inquiry_notify_test.py" %HOST%:/tmp/inquiry_notify_test.py >> "%LOG%" 2>&1
"%SSH%" -i "%KEY%" -o StrictHostKeyChecking=no %HOST% "docker cp /tmp/inquiry_notify_test.py leadgen_app:/app/scripts/inquiry_notify_test.py && docker exec leadgen_app python /app/scripts/inquiry_notify_test.py" >> "%LOG%" 2>&1
exit /b 0
