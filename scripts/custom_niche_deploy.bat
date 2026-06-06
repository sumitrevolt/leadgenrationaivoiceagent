@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del cn_deploy.log 2>nul

echo === COMMIT+PUSH === > cn_deploy.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> cn_deploy.log 2>&1
call "%GIT%" commit -m "feat(niches): custom niches at runtime - add/remove via API (admin), JSON persistence + mtime reload, KB auto-seed, tier C grouping in web-call; flows/agents/resolution work automatically; 4 new tests (80 total)" >> cn_deploy.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> cn_deploy.log
call "%GIT%" push origin main >> cn_deploy.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> cn_deploy.log

echo === VPS DEPLOY + CUSTOM-NICHE TEST === >> cn_deploy.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && echo ---CUSTOM-NICHE-E2E--- && timeout 60 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/vps_custom_niche_test.py 2>&1 | tail -8 && echo ---API-COUNT--- && curl -s -m 8 'http://127.0.0.1:8000/api/data/niches' | python3 -c 'import json,sys; print(\"count:\", json.load(sys.stdin)[\"count\"])'" >> cn_deploy.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> cn_deploy.log
echo CN_DONE
