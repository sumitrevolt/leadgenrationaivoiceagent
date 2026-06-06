@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del agents_deploy.log 2>nul

echo === COMMIT+PUSH === > agents_deploy.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> agents_deploy.log 2>&1
call "%GIT%" commit -m "feat(onboarding): auto-provision 2 agents per client (data + leads) with KB seeding; agents.role column + safe migration; client onboarding API; web-call dropdown serves all 25 niches dynamically; 15 new tests" >> agents_deploy.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> agents_deploy.log
call "%GIT%" push origin main >> agents_deploy.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> agents_deploy.log

echo === VPS DEPLOY+PROVISION-TEST === >> agents_deploy.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && echo ---NICHES--- && curl -s -m 8 'http://127.0.0.1:8000/api/data/niches' | python3 -c 'import json,sys; print(\"count:\", json.load(sys.stdin)[\"count\"])' && echo ---TESTCALL-PAGE--- && curl -s -m 8 -o /dev/null -w 'HTTP %%{http_code}' http://127.0.0.1:8000/app/test-call && echo && echo ---PROVISION-TEST--- && timeout 90 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/vps_provision_test.py 2>&1 | tail -8" >> agents_deploy.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> agents_deploy.log
echo AD_DONE
