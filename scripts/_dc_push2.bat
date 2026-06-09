@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set GIT="C:\PROGRA~1\Git\cmd\git.exe"
%GIT% add scripts/vps_recon.sh scripts/vps_cutover_prep.sh scripts/_dc_push2.bat
%GIT% commit -m "chore(infra): VPS recon + zero-downtime cutover-prep scripts"
echo --- PUSH ---
%GIT% push origin HEAD:main
echo DONE_EXIT=%ERRORLEVEL%
