@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0all_vobiz_db.log

"%SCP%" -i "%KEY%" -o BatchMode=yes %~dp0check_all_vobiz_db.py %HOST%:/tmp/check_all_vobiz_db.py
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker cp /tmp/check_all_vobiz_db.py leadgen_app:/app/check_all_vobiz_db.py && docker exec leadgen_app python3 /app/check_all_vobiz_db.py" > "%LOG%" 2>&1
type "%LOG%"
