@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del v3.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; print('IMPORTS OK')" > v3.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> v3.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> v3.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> v3.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> v3.log 2>&1
call "%GIT%" reset --soft origin/main >> v3.log 2>&1
call "%GIT%" add -A >> v3.log 2>&1
call "%GIT%" commit -m "feat(growth-v3): research-backed customer-growth suite — review collection kit (pure-python QR + counter card), monthly Hinglish auto-report, database reactivation (win-back wa.me), WhatsApp drip sequences, brand kit (poster colors), CRM-lite + birthday wishes; marketing-first consistency sweep everywhere (banner/manifest/kit/dashboards)" >> v3.log 2>&1
call "%GIT%" push origin main >> v3.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> v3.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'marketing page: %%{http_code}\n' http://127.0.0.1:8000/app/marketing && timeout 60 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/v3_smoke.py 2>&1 | grep -aE 'REVIEWKIT|REPORT|REACT|DRIP|BRAND|CRM'" >> v3.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> v3.log
echo V3_DONE
