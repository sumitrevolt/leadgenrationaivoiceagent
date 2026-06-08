@echo off
REM Phase-3 billing metering + tenant white-label. Pull (no restart) + test.
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_phase3b.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\billing\usage.py app\middleware\tenant.py app\middleware\__init__.py app\telephony\call_manager.py app\api\customer_dashboard.py tests\test_phase3_billing_tenant.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(phase3-saas): minute-usage metering + prepaid enforcement (billing/usage.py, call_manager hook+gate) + multi-tenant white-label middleware (fail-open) + dashboard branding + tests" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull (NO restart) === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo === IMPORT CHECK === >> %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/check_import.py 2>&1 | tail -2" >> %LOG% 2>&1
echo === PYTEST (all new suites) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest tests/test_phase3_billing_tenant.py tests/test_phase3_voice.py tests/test_phase2_upgrades.py tests/test_telephony_upgrades.py -q -o asyncio_mode=auto 2>&1 | tail -16" >> %LOG% 2>&1
echo === DONE (not restarted) === >> %LOG%
