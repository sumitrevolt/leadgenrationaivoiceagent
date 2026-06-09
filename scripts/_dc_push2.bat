@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set GIT="C:\PROGRA~1\Git\cmd\git.exe"
%GIT% add CLAUDE.md docs/SESSION_LOG.md
%GIT% commit -m "docs: app fully containerized (leadgen_app live) - update memory + log"
echo --- PUSH ---
%GIT% push origin HEAD:main
echo DONE_EXIT=%ERRORLEVEL%
