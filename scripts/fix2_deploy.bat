@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fix2.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.agents import staff; print('run_member:', hasattr(staff,'run_member'), 'run_growth:', hasattr(staff,'run_growth'))" > fix2.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> fix2.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> fix2.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> fix2.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> fix2.log 2>&1
call "%GIT%" reset --soft origin/main >> fix2.log 2>&1
call "%GIT%" add -A >> fix2.log 2>&1
call "%GIT%" commit -m "fix(dashboard+staff): admin dashboard ab file-based REAL data return karta (DB demo-seed override hata — yahi purana SunVolt/230000 dikha raha tha) + staff.py truncation fix (run_growth + run_member dispatcher restore)" >> fix2.log 2>&1
call "%GIT%" push origin main >> fix2.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> fix2.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && systemctl stop leadgen; sleep 2; pkill -9 -f 'uvicorn' 2>/dev/null; find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; sleep 2; systemctl start leadgen && sleep 16 && systemctl is-active leadgen && echo ---DASH--- && curl -s -m 8 http://127.0.0.1:8000/api/admin/dashboard | head -c 260" >> fix2.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> fix2.log
echo FIX2_DONE
