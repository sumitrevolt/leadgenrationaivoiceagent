@echo off
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "bash /opt/leadgen/scripts/vps_start_call_loop.sh"
