@echo off
REM Lead-gen quality deploy: email verify + phone validate + outreach wiring. Log -> cowork_deploy7.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_deploy7.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\lead_scraper\email_verify.py app\lead_scraper\phone_validate.py app\platform\auto_outreach.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(leadgen): email-validator (MX) + phonenumbers; verify-before-send wired into auto_outreach (competitor-grade deliverability)" >> %LOG% 2>&1
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
echo === INSTALL email-validator + phonenumbers === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/pip install -q email-validator phonenumbers" >> %LOG% 2>&1
echo EXIT_PIP=%errorlevel% >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -c 'import email_validator, phonenumbers'" >> %LOG% 2>&1
echo EXIT_IMPORT=%errorlevel% >> %LOG%
echo === QA: prod_check (imports auto_outreach edit) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -6 /tmp/pc.log" >> %LOG% 2>&1
echo === HEALTH AGAIN === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === DONE === >> %LOG%
