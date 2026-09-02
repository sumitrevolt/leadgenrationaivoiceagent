@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
call C:\PROGRA~1\Git\cmd\git.exe add CLAUDE.md docs/SESSION_LOG.md scripts/push_docs.bat
call C:\PROGRA~1\Git\cmd\git.exe commit -m "docs - exotel voicebot deploy milestone"
call C:\PROGRA~1\Git\cmd\git.exe push origin main
echo PUSH_EXIT %ERRORLEVEL%
