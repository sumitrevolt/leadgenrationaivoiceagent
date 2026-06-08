@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del setup.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.marketing import clients_store, auto_content; from app.api import clients; print('IMPORTS OK')" > setup.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> setup.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> setup.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> setup.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> setup.log 2>&1
call "%GIT%" reset --soft origin/main >> setup.log 2>&1
call "%GIT%" add -A >> setup.log 2>&1
call "%GIT%" commit -m "feat(customer-ready): free OSM Overpass prospect scraper (no paid key, phone+google-search-link), per-client auto social-media engine (clients_store + auto_content daily 07:00 IST weekly plan + queue), client portal /app/clients (onboard + approve/copy/post), API /api/clients/*" >> setup.log 2>&1
call "%GIT%" push origin main >> setup.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> setup.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'clients page: %%{http_code}\n' http://127.0.0.1:8000/app/clients && timeout 80 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/setup_smoke.py 2>&1 | grep -aE 'CLIENT:|GEN_ITEMS:|DAILY:|QUEUE:|OSM:'" >> setup.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> setup.log
echo SETUP_DONE
