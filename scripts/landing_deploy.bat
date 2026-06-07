@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del ld.log 2>nul

echo === PYTEST === > ld.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> ld.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> ld.log

echo === LOCAL ROOT CHECK === >> ld.log
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8923 ^| findstr LISTENING') do taskkill /f /pid %%a > nul 2>&1
start "ls" /b cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8923 > nul 2>&1"
ping -n 11 127.0.0.1 > nul
curl.exe -s -m 8 -o nul -w "root: HTTP %%{http_code} type=%%{content_type}\n" http://127.0.0.1:8923/ >> ld.log 2>&1
curl.exe -s -m 8 -o nul -w "health: HTTP %%{http_code}\n" http://127.0.0.1:8923/health >> ld.log 2>&1
curl.exe -s -m 8 -o nul -w "api/status: HTTP %%{http_code}\n" http://127.0.0.1:8923/api/status >> ld.log 2>&1
curl.exe -s -m 8 -o nul -w "niches: HTTP %%{http_code}\n" http://127.0.0.1:8923/api/data/niches >> ld.log 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8923 ^| findstr LISTENING') do taskkill /f /pid %%a > nul 2>&1

echo === COMMIT+PUSH+DEPLOY === >> ld.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add app/main.py scripts/landing_deploy.bat scripts/launch_ld.bat >> ld.log 2>&1
call "%GIT%" commit -m "feat(web): marketing website at root (/) via tail StaticFiles mount; JSON status moved to /api/status" >> ld.log 2>&1
call "%GIT%" push origin main >> ld.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> ld.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 10 && curl -s -m 8 -o /dev/null -w 'root: %%{http_code} %%{content_type}\n' http://127.0.0.1:8000/ && curl -s -m 8 -o /dev/null -w 'status: %%{http_code}\n' http://127.0.0.1:8000/api/status && curl -s -m 8 -o /dev/null -w 'testcall: %%{http_code}\n' http://127.0.0.1:8000/app/test-call" >> ld.log 2>&1
echo VPS_EXIT_%ERRORLEVEL% >> ld.log
echo LD_DONE >> ld.log
echo LD_DONE
