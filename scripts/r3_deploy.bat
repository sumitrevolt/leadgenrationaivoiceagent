@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del r3.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; print('IMPORTS OK')" > r3.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> r3.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> r3.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> r3.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> r3.log 2>&1
call "%GIT%" reset --soft origin/main >> r3.log 2>&1
call "%GIT%" add -A >> r3.log 2>&1
call "%GIT%" commit -m "feat(growth-r3): UPI payment kit (upi:// QR + slip), catalog/price-list builder, Google RSA + Meta ads copy pack (hard char limits), Reels script generator, rules-based lead scoring (hot/warm/cold), GBP description/services texts (Q&A API obsolete) — 5 new tabs, 12 tests" >> r3.log 2>&1
call "%GIT%" push origin main >> r3.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> r3.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'marketing page: %%{http_code}\n' http://127.0.0.1:8000/app/marketing && timeout 60 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/r3_smoke.py 2>&1 | grep -aE 'UPI:|CATALOG:|ADS:|REELS:|SCORING:|GBP:'" >> r3.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> r3.log
echo R3_DONE
