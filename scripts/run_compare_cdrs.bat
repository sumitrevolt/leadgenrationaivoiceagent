@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0compare_cdrs.log

"%SCP%" -i "%KEY%" -o BatchMode=yes %~dp0compare_cdrs.py %HOST%:/tmp/compare_cdrs.py
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "python3 /tmp/compare_cdrs.py" > "%LOG%" 2>&1
type "%LOG%"
