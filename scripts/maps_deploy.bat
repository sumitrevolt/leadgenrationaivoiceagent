@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del maps.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.platform import prospector; print('IMPORTS OK', hasattr(prospector,'build_personalized_pitch'))" > maps.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> maps.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> maps.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> maps.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> maps.log 2>&1
call "%GIT%" reset --soft origin/main >> maps.log 2>&1
call "%GIT%" add -A >> maps.log 2>&1
call "%GIT%" commit -m "feat(prospecting): real Google Maps scraping (phone+rating+reviews via Place Details, cost-capped PROSPECT_MAX_LOOKUPS) + auto-personalized Hinglish pitch from real Google data (low-reviews/no-website hooks + free audit CTA)" >> maps.log 2>&1
call "%GIT%" push origin main >> maps.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> maps.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && timeout 70 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/maps_smoke.py 2>&1 | grep -aE 'KEY_SET|LEADS|WITH_PHONE|SAMPLE|PITCH'" >> maps.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> maps.log
echo MAPS_DONE
