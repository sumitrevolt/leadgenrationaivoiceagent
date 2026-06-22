@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fix_redeploy.log 2>nul

echo === PYTEST === > fix_redeploy.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=no >> fix_redeploy.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> fix_redeploy.log

echo === COMMIT+PUSH === >> fix_redeploy.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add app/utils/logger.py scripts/vps_deploy_run.bat scripts/vps_check.bat scripts/fix_push_redeploy.bat >> fix_redeploy.log 2>&1
call "%GIT%" commit -m "fix: cloud-logging init must not retry/block startup without GCP creds (production VPS hang)" >> fix_redeploy.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> fix_redeploy.log
call "%GIT%" push origin main >> fix_redeploy.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> fix_redeploy.log

echo === VPS PULL+RESTART === >> fix_redeploy.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all && git reset --hard origin/main && systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && echo ---HEALTH--- && curl -s -m 8 http://127.0.0.1:8000/health" >> fix_redeploy.log 2>&1
echo REDEPLOY_EXIT_%ERRORLEVEL% >> fix_redeploy.log
echo ALL_DONE
