@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0fs_originate.log

"%SCP%" -i "%KEY%" -o BatchMode=yes %~dp0test_fs_originate.py %HOST%:/tmp/test_fs_originate.py
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "python3 /tmp/test_fs_originate.py" > "%LOG%" 2>&1
type "%LOG%"
