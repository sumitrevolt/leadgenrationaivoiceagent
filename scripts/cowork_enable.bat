@echo off
REM Enable safe feature flags + restart + verify + smoke. Log -> cowork_enable.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_enable.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === push tools === > %LOG%
call python -m py_compile scripts\enable_flags.py scripts\smoke_features.py >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "tools: enable_flags + smoke_features (activate safe automation)" >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo === ENABLE FLAGS (.env) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/enable_flags.py" >> %LOG% 2>&1
echo === RESTART === >> %LOG%
call %SSH% "systemctl restart leadgen" >> %LOG% 2>&1
ping -n 9 127.0.0.1 >nul
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === CONFIRM FLAGS (setup audit) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/setup_status.py 2>&1 | grep -E 'Flags ON|REPLY_AGENT|OPS_WATCHDOG|AUTO_ONBOARD|USE_STRUCTURED'" >> %LOG% 2>&1
echo === SMOKE-TEST FEATURES === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/smoke_features.py" >> %LOG% 2>&1
echo === DONE === >> %LOG%
