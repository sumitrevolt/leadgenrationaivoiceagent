@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set GIT=C:\PROGRA~1\Git\cmd\git.exe
del /q scripts\ship_rbac.log 2>nul
%GIT% add CLAUDE.md docs/SESSION_LOG.md > scripts\push_docs_rbac.log 2>&1
%GIT% commit -m "memory update, team rbac live" >> scripts\push_docs_rbac.log 2>&1
%GIT% push origin main >> scripts\push_docs_rbac.log 2>&1
%GIT% log -1 --oneline >> scripts\push_docs_rbac.log 2>&1
echo DONE >> scripts\push_docs_rbac.log
