@echo off
REM Fix duplicate routes — revert dup modules/endpoints, keep content scheduler + clean festival glue.
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_fix.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\api\marketing.py app\marketing\content_schedule.py app\voice_agent\free_ai.py scripts\check_fix.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "fix(marketing): revert duplicate routes/modules (review-reply, festivals, ads, reels, gbp already existed) — keep content scheduler + clean festival-autoschedule glue" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
ping -n 8 127.0.0.1 >nul
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === QA prod_check === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -3 /tmp/pc.log" >> %LOG% 2>&1
echo === VERIFY (no dup routes, existing intact) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/check_fix.py" >> %LOG% 2>&1
echo === DONE === >> %LOG%
