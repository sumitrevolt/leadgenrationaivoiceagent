@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker logs leadgen_app --since 15m 2>&1 | grep -iE 'vobiz|stream|PLACED|transcript|call_' | tail -40"

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app ls -la data/call_transcripts/ 2>/dev/null; docker exec leadgen_app tail -3 data/call_transcripts/2026-06-21.jsonl 2>/dev/null || echo no_today_transcript"

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app tail -5 data/skill_lessons.jsonl 2>/dev/null"
