@echo off
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set ROOT=c:\Users\Ratanshila\Documents\leadgenrationaiagent\scripts\..

"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\app\voice_agent\telecaller_brain.py" root@72.61.245.204:/tmp/telecaller_brain.py
"%SSH%" -i "%KEY%" -o BatchMode=yes root@72.61.245.204 "docker cp /tmp/telecaller_brain.py leadgen_app:/app/app/voice_agent/telecaller_brain.py && docker compose -f /opt/leadgen/docker-compose.vps.yml restart app"
