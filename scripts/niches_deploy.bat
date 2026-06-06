@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del niches_deploy.log 2>nul

echo === PYTEST === > niches_deploy.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=short >> niches_deploy.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> niches_deploy.log

echo === PRODCHECK === >> niches_deploy.log
.venv\Scripts\python.exe scripts\prod_check.py >> niches_deploy.log 2>&1
echo PRODCHECK_EXIT_%ERRORLEVEL% >> niches_deploy.log

echo === COMMIT+PUSH === >> niches_deploy.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add app/niches.py app/api/data.py scripts/build_pricing_xlsx.py scripts/build_xlsx.bat scripts/niches_deploy.bat Niche_Pricing_Research.xlsx >> niches_deploy.log 2>&1
call "%GIT%" commit -m "feat(niches): research-finalized top 25 niches with two-tier B2B/B2C targeting + INR pricing bands; niches API filters (target_type/tier); pricing research workbook" >> niches_deploy.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> niches_deploy.log
call "%GIT%" push origin main >> niches_deploy.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> niches_deploy.log

echo === VPS PULL+RESTART+VERIFY === >> niches_deploy.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && curl -s -m 8 'http://127.0.0.1:8000/api/data/niches' | head -c 120 && echo && curl -s -m 8 'http://127.0.0.1:8000/api/data/niches?tier=S' | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"S-tier count:\", d[\"count\"])' && curl -s -m 8 'http://127.0.0.1:8000/api/data/niches?target_type=b2c' | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"B2C count:\", d[\"count\"])'" >> niches_deploy.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> niches_deploy.log
echo ND_DONE
