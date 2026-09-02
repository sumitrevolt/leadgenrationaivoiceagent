@echo off
setlocal
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0vps_call_learn_run.log
set ROOT=c:\Users\Ratanshila\Documents\leadgenrationaiagent

echo run >> "%LOG%"

"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\scripts\voice_learn_from_calls.py" %HOST%:/tmp/voice_learn_from_calls.py >> "%LOG%" 2>&1
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker cp /tmp/voice_learn_from_calls.py leadgen_app:/app/scripts/voice_learn_from_calls.py" >> "%LOG%" 2>&1

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 scripts/voice_learn_from_calls.py --call-limit 1 --platform --wait 180 --limit 2" >> "%LOG%" 2>&1

type "%LOG%"
