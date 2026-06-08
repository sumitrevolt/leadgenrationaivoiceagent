@echo off
REM P2 Customer login portal. Pull (no restart) + test, then restart + smoke.
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_p2.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\api\customer_auth.py app\main.py tests\test_customer_portal.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(P2): customer login portal — /app/login + /api/customer/auth/* (JWT role=customer, pbkdf2, separate cred store, non-breaking) + token-gated portal dashboard + tests" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull (NO restart) === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo === IMPORT CHECK === >> %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/check_import.py 2>&1 | tail -2" >> %LOG% 2>&1
echo === PYTEST === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest tests/test_customer_portal.py -q -o asyncio_mode=auto 2>&1 | tail -14" >> %LOG% 2>&1
echo === RESTART + smoke === >> %LOG%
call %SSH% "systemctl restart leadgen" >> %LOG% 2>&1
ping -n 9 127.0.0.1 >nul
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "echo -n 'health='; curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/health; echo -n ' login_page='; curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/app/login; echo -n ' bad_login='; curl -s -o /dev/null -w '%%{http_code}' -X POST http://127.0.0.1:8000/api/customer/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"no@no.com\",\"password\":\"x\"}'; echo" >> %LOG% 2>&1
echo === DONE === >> %LOG%
