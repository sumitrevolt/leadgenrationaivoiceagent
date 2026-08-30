@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0probe_trunk.log

"%SCP%" -i "%KEY%" -o BatchMode=yes %~dp0probe_trunk_and_fs.py %HOST%:/tmp/probe_trunk_and_fs.py
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "python3 /tmp/probe_trunk_and_fs.py" > "%LOG%" 2>&1
type "%LOG%"
