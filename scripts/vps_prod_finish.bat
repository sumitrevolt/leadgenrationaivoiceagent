@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204

"%SSH%" -i "%KEY%" -o StrictHostKeyChecking=no -o BatchMode=yes %HOST% "bash /opt/leadgen/scripts/vps_prod_finish.sh"
exit /b %ERRORLEVEL%
