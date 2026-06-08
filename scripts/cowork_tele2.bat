@echo off
REM Telephony hardening — verified import, restart, prod_check, regression. Log -> cowork_tele2.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_tele2.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === IMPORT CHECK (PYTHONPATH=.) === > %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/check_import.py 2>&1 | tail -8" >> %LOG% 2>&1
echo === RESTART === >> %LOG%
call %SSH% "cd /opt/leadgen && systemctl restart leadgen" >> %LOG% 2>&1
ping -n 9 127.0.0.1 >nul
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === telephony health route (newly mounted) === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/api/webhooks/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === prod_check === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -3 /tmp/pc.log" >> %LOG% 2>&1
echo === full pytest (regression) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest -q 2>&1 | tail -15" >> %LOG% 2>&1
echo === DONE === >> %LOG%
