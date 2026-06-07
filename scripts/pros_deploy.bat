@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del pros.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.platform import prospector; print('IMPORTS OK')" > pros.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> pros.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> pros.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> pros.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> pros.log 2>&1
call "%GIT%" reset --soft origin/main >> pros.log 2>&1
call "%GIT%" add -A >> pros.log 2>&1
call "%GIT%" commit -m "feat(growth-auto): Rohan auto-prospecting (daily 09:30 scrape+dedupe+pitch+wa.me queue), outreach dashboard /app/outreach (one-click send + status), inquiry auto-callback via AI call (AUTO_CALLBACK_INQUIRY, graceful when telephony unfunded)" >> pros.log 2>&1
call "%GIT%" push origin main >> pros.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> pros.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline | head -c 60 && echo && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'outreach page: %%{http_code}\n' http://127.0.0.1:8000/app/outreach" >> pros.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> pros.log
echo PROS_DONE
