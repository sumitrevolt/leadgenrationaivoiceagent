@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0vobiz_run_check.log

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "python3 /tmp/test_vobiz_auth_methods.py" > "%LOG%" 2>&1
type "%LOG%"
