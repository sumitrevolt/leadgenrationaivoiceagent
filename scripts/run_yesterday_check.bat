@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0yesterday_calls.log

"%SCP%" -i "%KEY%" -o BatchMode=yes %~dp0check_yesterday_calls.py %HOST%:/tmp/check_yesterday_calls.py
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker cp /tmp/check_yesterday_calls.py leadgen_app:/app/check_yesterday_calls.py && docker exec leadgen_app python3 /app/check_yesterday_calls.py" > "%LOG%" 2>&1
type "%LOG%"
