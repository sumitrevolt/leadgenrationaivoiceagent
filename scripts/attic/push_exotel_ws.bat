@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
call C:\PROGRA~1\Git\cmd\git.exe add app/voice_agent/exotel_stream.py app/voice_agent/phone_stream.py app/main.py tests/test_exotel_stream.py tests/test_infra_batch2.py CLAUDE.md docs/SESSION_LOG.md scripts/push_exotel_ws.bat
call C:\PROGRA~1\Git\cmd\git.exe commit -m "exotel voicebot websocket stream handler, stale roster test fix"
call C:\PROGRA~1\Git\cmd\git.exe push origin main
echo PUSH_EXIT %ERRORLEVEL%
