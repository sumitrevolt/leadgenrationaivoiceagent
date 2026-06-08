@echo off
REM Auto client onboarding orchestrator + scheduler. Log -> cowork_deploy10.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_deploy10.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\marketing\onboarding.py app\platform\team_scheduler.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(automation): auto client onboarding orchestrator (website->KB seed + content pack) + hourly sweep, gated AUTO_ONBOARD" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
echo EXIT_PULL=%errorlevel% >> %LOG%
ping -n 8 127.0.0.1 >nul
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === QA: prod_check (validates real clients_store + onboarding + scheduler) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -7 /tmp/pc.log" >> %LOG% 2>&1
echo === DONE === >> %LOG%
