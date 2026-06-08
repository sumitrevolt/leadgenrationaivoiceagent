@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del sch.log 2>nul
.venv\Scripts\python.exe -c "from app.platform import team_scheduler as t; print('LOCKFNS', hasattr(t,'_acquire_lock') and hasattr(t,'_refresh_lock'))" > sch.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> sch.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> sch.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> sch.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> sch.log 2>&1
call "%GIT%" reset --soft origin/main >> sch.log 2>&1
call "%GIT%" add -A >> sch.log 2>&1
call "%GIT%" commit -m "fix(scheduler): single-instance lock — uvicorn 2 workers dono scheduler chala rahe the (double emails/content/jobs). Ab lock-file (heartbeat + dead-pid reclaim) se sirf 1 worker chalata hai" >> sch.log 2>&1
call "%GIT%" push origin main >> sch.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> sch.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && rm -f data/.scheduler.lock; systemctl stop leadgen; sleep 2; pkill -9 -f uvicorn 2>/dev/null; find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; sleep 2; systemctl start leadgen" >> sch.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> sch.log
echo SCH_DONE
