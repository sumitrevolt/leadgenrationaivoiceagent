@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del sch2.log 2>nul
.venv\Scripts\python.exe -m pytest tests/test_production_gaps.py tests/test_growth_engine.py -q --no-header -p no:cacheprovider --tb=line > sch2.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> sch2.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> sch2.log 2>&1
call "%GIT%" commit -m "fix(scheduler): single-instance lock (2-worker double-jobs fix)" >> sch2.log 2>&1
call "%GIT%" push origin main >> sch2.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> sch2.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && rm -f data/.scheduler.lock; systemctl stop leadgen; sleep 2; pkill -9 -f uvicorn 2>/dev/null; find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; sleep 2; systemctl start leadgen" >> sch2.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> sch2.log
echo SCH2_DONE
