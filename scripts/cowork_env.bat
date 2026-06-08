@echo off
REM P1+P3: set safe .env keys on VPS, restart, verify. Log -> cowork_env.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_env.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === push env_set.py === > %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "chore(env): idempotent env_set.py for P1 revenue + P3 dormant flags (no secrets)" >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo === VPS pull + set env === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && PYTHONPATH=. .venv/bin/python scripts/env_set.py" >> %LOG% 2>&1
echo === restart === >> %LOG%
call %SSH% "systemctl restart leadgen" >> %LOG% 2>&1
ping -n 9 127.0.0.1 >nul
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === P1 verify: pay-info === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/api/public/pay-info" >> %LOG% 2>&1
echo. >> %LOG%
echo === setup_status (flags) === >> %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/setup_status.py 2>&1 | tail -20" >> %LOG% 2>&1
echo === DONE === >> %LOG%
