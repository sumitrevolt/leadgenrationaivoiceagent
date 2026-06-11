@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
%SSH% -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 "cd /opt/leadgen && docker compose -f docker-compose.vps.yml build app 2>&1 | tail -50" > scripts\diag_build.log 2>&1
echo BATDONE >> scripts\diag_build.log
