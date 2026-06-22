@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set GIT=C:\PROGRA~1\Git\cmd\git.exe
del /q scripts\smoke_skillpack.bat scripts\smoke_ingest.bat scripts\probe_build.bat scripts\diag_build.bat scripts\push_dockerfix.bat 2>nul
del /q scripts\*.log 2>nul
%GIT% rm -q --cached scripts/diag_build.bat scripts/push_dockerfix.bat > scripts\final_docs_push.log 2>&1
%GIT% add CLAUDE.md docs/SESSION_LOG.md >> scripts\final_docs_push.log 2>&1
%GIT% commit -m "session log and memory update, skill pack code upgrader live, one-off scripts cleanup" >> scripts\final_docs_push.log 2>&1
%GIT% push origin main >> scripts\final_docs_push.log 2>&1
%GIT% log -1 --oneline >> scripts\final_docs_push.log 2>&1
echo DONE >> scripts\final_docs_push.log
