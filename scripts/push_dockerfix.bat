@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set GIT=C:\PROGRA~1\Git\cmd\git.exe
%GIT% add Dockerfile.lock scripts/deploy_skillpack.bat scripts/diag_build.bat scripts/push_dockerfix.bat > scripts\push_dockerfix.log 2>&1
%GIT% commit -m "dockerfile pip retries and copy claude skills into image" >> scripts\push_dockerfix.log 2>&1
%GIT% push origin main >> scripts\push_dockerfix.log 2>&1
%GIT% log -1 --oneline >> scripts\push_dockerfix.log 2>&1
echo DONE >> scripts\push_dockerfix.log
