@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0vps_test_call_user.log
set ROOT=c:\Users\Ratanshila\Documents\leadgenrationaiagent

echo test call +918459012607 > "%LOG%"

"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\scripts\voice_learn_from_calls.py" %HOST%:/tmp/voice_learn_from_calls.py >> "%LOG%" 2>&1
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker cp /tmp/voice_learn_from_calls.py leadgen_app:/app/scripts/voice_learn_from_calls.py" >> "%LOG%" 2>&1

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 -c \"import asyncio; from app.api.telephony_vobiz import start_stream_call; r=asyncio.run(start_stream_call(to='+918459012607', niche='ai_marketing', call_type='transactional')); print(r)\"" >> "%LOG%" 2>&1

echo waiting 200s for call+transcript >> "%LOG%"
ping -n 201 127.0.0.1 >nul

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 scripts/voice_learn_from_calls.py --learn-only --limit 3" >> "%LOG%" 2>&1

type "%LOG%"
