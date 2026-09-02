@echo off
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set ROOT=c:\Users\Ratanshila\Documents\leadgenrationaiagent

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "pkill -f fire_calls_loop.py 2>/dev/null; rm -f /opt/leadgen/data/call_loop.pid; echo loop_off"

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "mkdir -p /tmp/voice_deploy"

"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\app\voice_agent\telecaller_brain.py" %HOST%:/tmp/voice_deploy/telecaller_brain.py
"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\app\voice_agent\platform_pitch.py" %HOST%:/tmp/voice_deploy/platform_pitch.py
"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\app\voice_agent\niche_scripts_data.py" %HOST%:/tmp/voice_deploy/niche_scripts_data.py
"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\app\telephony\vobiz_stream.py" %HOST%:/tmp/voice_deploy/vobiz_stream.py
"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\app\api\telephony_vobiz.py" %HOST%:/tmp/voice_deploy/telephony_vobiz.py
"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\scripts\fire_calls.py" %HOST%:/tmp/voice_deploy/fire_calls.py

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker cp /tmp/voice_deploy/telecaller_brain.py leadgen_app:/app/app/voice_agent/telecaller_brain.py && docker cp /tmp/voice_deploy/platform_pitch.py leadgen_app:/app/app/voice_agent/platform_pitch.py && docker cp /tmp/voice_deploy/niche_scripts_data.py leadgen_app:/app/app/voice_agent/niche_scripts_data.py && docker cp /tmp/voice_deploy/vobiz_stream.py leadgen_app:/app/app/telephony/vobiz_stream.py && docker cp /tmp/voice_deploy/telephony_vobiz.py leadgen_app:/app/app/api/telephony_vobiz.py && docker cp /tmp/voice_deploy/fire_calls.py leadgen_app:/app/scripts/fire_calls.py && docker compose -f /opt/leadgen/docker-compose.vps.yml restart app"

echo DEPLOY_DONE_NO_LOOP
