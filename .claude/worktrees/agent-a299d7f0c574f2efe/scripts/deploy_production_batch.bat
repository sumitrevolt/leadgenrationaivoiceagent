@echo off
setlocal
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set VPS=root@72.61.245.204
set ROOT=c:\Users\Ratanshila\Documents\leadgenrationaiagent

echo === SCP files to VPS ===
"%SCP%" -i "%KEY%" "%ROOT%\frontend\explorer.html" "%VPS%:/opt/leadgen/frontend/explorer.html"
"%SCP%" -i "%KEY%" "%ROOT%\frontend\automation.html" "%VPS%:/opt/leadgen/frontend/automation.html"
"%SCP%" -i "%KEY%" "%ROOT%\app\api\activation.py" "%VPS%:/opt/leadgen/app/api/activation.py"
"%SCP%" -i "%KEY%" "%ROOT%\scripts\production_ready.py" "%VPS%:/opt/leadgen/scripts/production_ready.py"
"%SCP%" -i "%KEY%" "%ROOT%\scripts\vps_production_harden.sh" "%VPS%:/opt/leadgen/scripts/vps_production_harden.sh"
"%SCP%" -i "%KEY%" "%ROOT%\app\telephony\vobiz_stream.py" "%VPS%:/opt/leadgen/app/telephony/vobiz_stream.py"
if errorlevel 1 goto fail

echo === rebuild app container ===
"%SSH%" -i "%KEY%" -o BatchMode=yes %VPS% "cd /opt/leadgen && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app && sleep 16 && curl -sf http://127.0.0.1:8000/health && curl -sf http://127.0.0.1:8000/api/activation/summary"
if errorlevel 1 goto fail

echo === DONE ===
exit /b 0
:fail
echo DEPLOY FAILED
exit /b 1
